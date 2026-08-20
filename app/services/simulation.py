"""Executes a compiled_graph_object as a SimPy discrete-event simulation.

v1 scope and simplifications (deliberately narrow -- see docs/planning/00-overview.md
roadmap; extend these as real usage demands it):

- Only flow_type in {sequential, parallel, merge} drives execution. Transition
  `condition` strings are stored but never evaluated (matches
  COMPILER_MAPPING_RULE.transition_compilation_rules: a non-empty condition is
  documented as "application_defined_expression", i.e. undefined without a rule
  engine -- out of scope here).
- A step can declare multiple named outputs with fixed ratios (ProcessStepOutput)
  -- e.g. one input yielding two co-products at a 6:4 split (docs/planning/
  07-schema-gap-review.md). Transitions carrying the same output_item_id from a
  step still divide that item's qty equally among them. A merge step's incoming
  transitions can each carry a different consumption_ratio (asymmetric BOM,
  e.g. 2 units of A per 1 unit of B) instead of always consuming 1:1.
- Continuous steps process in chunks of up to CHUNK_QTY_CAP units per
  resource-hold cycle (not unit-by-unit) so a 30-day run stays a few hundred
  events per step instead of millions. Batch steps process exactly one batch
  per cycle. setup_time is charged as a changeover cost: once whenever a
  resource_key's last-processed step_no differs from the step now acquiring
  it (docs/planning/07-schema-gap-review.md 3-4), not just on a step's very
  first cycle. A step that has its equipment_group all to itself therefore
  still only ever pays setup once (nothing else changes the resource's
  identity), matching the old behavior; it repeats only when steps sharing
  the same resource_key actually alternate. Steps with no bound resource
  keep the strict "once ever" rule, since there's no resource identity to
  key a changeover off of. For a resource pool with capacity > 1, a single
  last-identity is tracked for the whole pool rather than per physical
  unit -- a deliberate approximation, not per-unit changeover tracking.
- Lead time is estimated via Little's Law (avg_wip / throughput_rate), not by
  tracking individual unit dwell time -- there's no per-unit identity in this
  chunked model.
- scenario_toggles (breakdown/PM/defect/rework/shift-calendar) are accepted
  but ignored: none are implemented yet, consistent with them defaulting to
  False in SIMPY_RUNTIME_META.
- If two source steps both draw from the same material_inbound_plan, each
  gets an independent copy of that supply (no shared-supply contention). Real
  topologies typically have one entry point per raw material; revisit if that
  changes.
"""

import simpy

CHUNK_QTY_CAP = 500

_MINUTES_PER_UNIT = {"minute": 1, "hour": 60, "day": 24 * 60}


def _to_minutes(value: float, unit: str) -> float:
    return value * _MINUTES_PER_UNIT.get(unit, _MINUTES_PER_UNIT["day"])


def _match_inbound_plan(step: dict, plans: list[dict]) -> dict | None:
    candidates = [p for p in plans if p["item_id"] == step["input_item_id"]]
    if not candidates:
        return None
    if step.get("input_location_id"):
        for plan in candidates:
            if plan["location_id"] == step["input_location_id"]:
                return plan
    return candidates[0]


def run_simulation(
    compiled_graph_object: dict,
    time_control: dict,
    output_control: dict,
    inbound_plans: list[dict],
    inbound_overrides: dict[str, float] | None = None,
) -> dict:
    nodes = {n["step_no"]: n for n in compiled_graph_object["nodes"]}
    proc_by_step = {p["step_no"]: p for p in compiled_graph_object["processing_time_plan"]}
    queue_by_step = {q["step_no"]: q for q in compiled_graph_object["queue_plan"]}
    resource_key_by_step = {
        rb["step_no"]: rb["resource_key"] for rb in compiled_graph_object["resource_bindings"]
    }
    resource_capacity = {
        rb["resource_key"]: rb["capacity"] for rb in compiled_graph_object["resource_bindings"]
    }

    predecessors: dict[str, list[str]] = {step_no: [] for step_no in nodes}
    transitions_by_from: dict[str, list[dict]] = {step_no: [] for step_no in nodes}
    transitions_by_to: dict[str, list[dict]] = {step_no: [] for step_no in nodes}
    for t in compiled_graph_object["transitions"]:
        predecessors[t["to_step_no"]].append(t["from_step_no"])
        transitions_by_from[t["from_step_no"]].append(t)
        transitions_by_to[t["to_step_no"]].append(t)

    end_time = _to_minutes(time_control.get("duration_days", 30), "day")
    inbound_overrides = inbound_overrides or {}

    env = simpy.Environment()

    containers: dict[str, dict[str, simpy.Container]] = {}
    for step_no, node in nodes.items():
        capacity = queue_by_step.get(step_no, {}).get("capacity") or float("inf")
        preds = predecessors[step_no]
        if preds:
            containers[step_no] = {p: simpy.Container(env, capacity=capacity, init=0) for p in preds}
        else:
            containers[step_no] = {"__inbound__": simpy.Container(env, capacity=capacity, init=0)}

    resources = {key: simpy.Resource(env, capacity=cap) for key, cap in resource_capacity.items()}

    event_log: list[dict] = []
    wip_snapshots: list[dict] = []
    busy_time_by_resource = {key: 0.0 for key in resources}
    # resource_key -> step_no that last held it; a changeover (and setup_time) is charged
    # whenever the step now acquiring the resource differs from this (see step_process).
    resource_last_identity: dict[str, str] = {}

    def put_downstream(from_step_no: str, qty: float):
        """Split qty across this step's declared outputs (by output_ratio), then across whichever
        transitions carry each output item (equally, among transitions sharing that output_item_id).
        An output item with no matching outgoing transition exits the network (byproduct/finished good).
        """
        outgoing = transitions_by_from[from_step_no]
        outputs = nodes[from_step_no]["outputs"]
        single_output = len(outputs) == 1

        for output in outputs:
            item_qty = qty * output["output_ratio"]
            matching = [
                t
                for t in outgoing
                if t["output_item_id"] == output["output_item_id"]
                or (t["output_item_id"] is None and single_output)
            ]
            if not matching:
                event_log.append(
                    {
                        "sim_time": env.now,
                        "event_type": "exit",
                        "step_no": from_step_no,
                        "item_id": output["output_item_id"],
                        "qty": item_qty,
                    }
                )
                continue
            share = item_qty / len(matching)
            for t in matching:
                yield containers[t["to_step_no"]][from_step_no].put(share)

    def step_process(step_no: str):
        node = nodes[step_no]
        proc = proc_by_step[step_no]
        is_merge = node["flow_type"] == "merge"
        is_batch = node["production_type"] == "batch"
        std_time_per = proc["std_time_per"]
        setup_time = proc.get("setup_time") or 0
        unbound_setup_pending = setup_time > 0  # only meaningful when resource is None, see below
        batch_size = node.get("batch_size") or 1
        # input_qty_per (recipe length_factor fallback, see app/services/compiler.py
        # _select_recipe) scales how much is consumed from a *single* input container per
        # unit of output -- the non-merge analogue of a merge transition's consumption_ratio.
        input_per_output = proc.get("input_qty_per") or 1.0
        loss_rate = proc.get("loss_rate") or 0.0
        resource_key = resource_key_by_step.get(step_no)
        resource = resources.get(resource_key)
        step_containers = containers[step_no]
        consumption_ratio_by_pred = {t["from_step_no"]: t["consumption_ratio"] for t in transitions_by_to[step_no]}

        while True:
            if is_merge:
                # Production and consumption are decoupled: this cycle always *produces* one
                # unit/batch, but each predecessor may be consumed at a different ratio (e.g. a
                # 2:1 BOM) via the incoming transition's consumption_ratio.
                output_qty = batch_size if is_batch else 1
                for pred_step_no, container in step_containers.items():
                    ratio = consumption_ratio_by_pred.get(pred_step_no, 1.0)
                    yield container.get(output_qty * ratio)
                qty = output_qty
            else:
                container = next(iter(step_containers.values()))
                if is_batch:
                    yield container.get(batch_size * input_per_output)
                    qty = batch_size
                else:
                    yield container.get(input_per_output)
                    qty = 1
                    extra = min(container.level / input_per_output, CHUNK_QTY_CAP - 1)
                    if extra > 0:
                        yield container.get(extra * input_per_output)
                        qty += extra

            base_time = (qty / batch_size if is_batch else qty) * std_time_per

            if resource is not None:
                with resource.request() as req:
                    yield req
                    # Changeover: charge setup_time whenever the resource's last-processed
                    # step differs from this one (including the very first-ever acquisition).
                    # A step with sole use of its resource therefore still only pays setup once.
                    changeover = resource_last_identity.get(resource_key) != step_no
                    resource_last_identity[resource_key] = step_no
                    applied_setup_time = setup_time if changeover else 0
                    proc_time = base_time + applied_setup_time
                    start_time = env.now
                    yield env.timeout(proc_time)
                    busy_time_by_resource[resource_key] += env.now - start_time
            else:
                applied_setup_time = setup_time if unbound_setup_pending else 0
                unbound_setup_pending = False
                proc_time = base_time + applied_setup_time
                start_time = env.now
                yield env.timeout(proc_time)

            event_log.append(
                {
                    "sim_time": start_time,
                    "event_type": "process",
                    "step_no": step_no,
                    "resource_key": resource_key,
                    "qty": qty,
                }
            )
            if applied_setup_time > 0:
                # qty here is the setup/changeover duration, not a material quantity -- same
                # "reuse qty for the event's magnitude" convention as the "loss" event above,
                # since SimulationEventLog only persists a generic qty/item_id per event.
                event_log.append(
                    {
                        "sim_time": start_time,
                        "event_type": "setup",
                        "step_no": step_no,
                        "resource_key": resource_key,
                        "qty": applied_setup_time,
                    }
                )

            yield_qty = qty * (1 - loss_rate)
            if loss_rate > 0:
                event_log.append(
                    {
                        "sim_time": start_time,
                        "event_type": "loss",
                        "step_no": step_no,
                        "qty": qty - yield_qty,
                    }
                )
            yield env.process(put_downstream(step_no, yield_qty))

    def inbound_process(step_no: str, plan: dict):
        container = containers[step_no]["__inbound__"]
        qty = inbound_overrides.get(plan["plan_id"], plan["inbound_qty"])
        interval_minutes = _to_minutes(plan["interval_value"], plan["interval_unit"])
        while True:
            yield container.put(qty)
            event_log.append(
                {"sim_time": env.now, "event_type": "inbound", "item_id": plan["item_id"], "qty": qty}
            )
            yield env.timeout(interval_minutes)

    def wip_snapshot_process(interval_minutes: float):
        while True:
            by_step = {step_no: sum(c.level for c in conts.values()) for step_no, conts in containers.items()}
            wip_snapshots.append({"sim_time": env.now, "total_wip": sum(by_step.values()), "by_step": by_step})
            yield env.timeout(interval_minutes)

    for step_no, node in nodes.items():
        env.process(step_process(step_no))
        if not predecessors[step_no]:
            plan = _match_inbound_plan(node, inbound_plans)
            if plan is not None:
                env.process(inbound_process(step_no, plan))

    if output_control.get("collect_wip_snapshot", True):
        snapshot_interval = _to_minutes(
            output_control.get("snapshot_interval", 60),
            output_control.get("snapshot_interval_unit", "minute"),
        )
        env.process(wip_snapshot_process(snapshot_interval))

    env.run(until=end_time)

    exit_qty = sum(e["qty"] for e in event_log if e["event_type"] == "exit")
    exit_qty_by_step: dict[str, float] = {}
    for e in event_log:
        if e["event_type"] == "exit":
            exit_qty_by_step[e["step_no"]] = exit_qty_by_step.get(e["step_no"], 0.0) + e["qty"]
    throughput_per_day = exit_qty / (end_time / _MINUTES_PER_UNIT["day"]) if end_time else 0.0
    avg_wip = sum(s["total_wip"] for s in wip_snapshots) / len(wip_snapshots) if wip_snapshots else None
    throughput_rate = exit_qty / end_time if end_time else 0.0
    avg_lead_time = (avg_wip / throughput_rate) if (avg_wip is not None and throughput_rate > 0) else None

    resource_utilization = {
        key: (busy / end_time if end_time else 0.0) for key, busy in busy_time_by_resource.items()
    }
    bottleneck_step_no = None
    if resource_utilization:
        bottleneck_resource = max(resource_utilization, key=resource_utilization.get)
        for step_no, key in resource_key_by_step.items():
            if key == bottleneck_resource:
                bottleneck_step_no = step_no
                break

    return {
        "event_log": event_log,
        "wip_snapshots": wip_snapshots,
        "summary": {
            "throughput_total": exit_qty,
            "throughput_per_day": throughput_per_day,
            "avg_wip": avg_wip,
            "avg_lead_time": avg_lead_time,
            "resource_utilization": resource_utilization,
            "bottleneck_step_no": bottleneck_step_no,
            "exit_qty_by_step": exit_qty_by_step,
        },
    }
