import pytest

from app.services.simulation import run_simulation

TIME_CONTROL_1_DAY = {"duration_days": 1}  # 1440 minutes
OUTPUT_CONTROL = {"collect_wip_snapshot": True, "snapshot_interval": 60, "snapshot_interval_unit": "minute"}


def _node(step_no, flow_type="sequential", production_type="continuous", batch_size=None, batch_unit=None, outputs=None):
    return {
        "step_no": step_no,
        "flow_type": flow_type,
        "production_type": production_type,
        "batch_size": batch_size,
        "batch_unit": batch_unit,
        "input_item_id": f"ITEM-IN-{step_no}",
        "outputs": outputs if outputs is not None else [{"output_item_id": f"ITEM-OUT-{step_no}", "output_ratio": 1.0, "unit": None}],
        "input_location_id": None,
    }


def _proc(step_no, std_time_per, setup_time=0, input_qty_per=None, loss_rate=0.0):
    return {
        "step_no": step_no,
        "std_time_per": std_time_per,
        "setup_time": setup_time,
        "input_qty_per": input_qty_per,
        "loss_rate": loss_rate,
    }


def _resource_binding(step_no, resource_key, capacity):
    return {"step_no": step_no, "resource_key": resource_key, "capacity": capacity}


def _transition(from_step_no, to_step_no, output_item_id=None, consumption_ratio=1.0):
    return {
        "from_step_no": from_step_no,
        "to_step_no": to_step_no,
        "output_item_id": output_item_id,
        "consumption_ratio": consumption_ratio,
    }


def _inbound_plan(plan_id, item_id, qty):
    return {
        "plan_id": plan_id,
        "item_id": item_id,
        "location_id": None,
        "inbound_qty": qty,
        "interval_value": 1,
        "interval_unit": "day",
    }


def test_single_sequential_step_processes_in_bounded_chunks():
    # 1 min/unit, resource capacity 1, effectively unlimited supply and queue capacity.
    # CHUNK_QTY_CAP=500 means each resource-hold cycle processes 500 units (500 minutes).
    # Over a 1440-minute run: cycle 1 completes at t=500, cycle 2 at t=1000, cycle 3
    # would finish at t=1500 (> 1440) so it never completes/logs -- exactly 1000 units exit.
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100_000)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["throughput_total"] == 1000
    assert result["summary"]["throughput_per_day"] == 1000
    process_events = [e for e in result["event_log"] if e["event_type"] == "process"]
    assert [e["qty"] for e in process_events] == [500, 500]
    assert result["summary"]["resource_utilization"]["R1"] > 0
    assert result["summary"]["bottleneck_step_no"] == "1"


def test_no_matching_inbound_plan_yields_zero_output():
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans=[])

    assert result["summary"]["throughput_total"] == 0
    assert result["event_log"] == []


def test_material_inbound_override_changes_supply():
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100_000)]

    # Cap supply to 300 (less than one full 500-unit chunk): only one cycle of 300 completes.
    result = run_simulation(
        graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans, inbound_overrides={"PLAN-1": 300}
    )

    assert result["summary"]["throughput_total"] == 300


def test_parallel_split_divides_output_equally():
    graph = {
        "nodes": [
            _node("1"),
            _node("2", flow_type="parallel"),
            _node("3", flow_type="parallel"),
        ],
        "transitions": [
            _transition("1", "2"),
            _transition("1", "3"),
        ],
        "resource_bindings": [
            _resource_binding("1", "R1", 1),
            _resource_binding("2", "R2", 1),
            _resource_binding("3", "R3", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0),
            _proc("2", std_time_per=1.0),
            _proc("3", std_time_per=1.0),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "2", "capacity": None},
            {"step_no": "3", "capacity": None},
        ],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    # Step 1 processes 100 units (all available on the one inbound delivery), splits 50/50
    # (its single output item feeds two transitions, divided equally between them).
    exits_by_step = {}
    for e in result["event_log"]:
        if e["event_type"] == "exit":
            exits_by_step[e["step_no"]] = exits_by_step.get(e["step_no"], 0) + e["qty"]
    assert exits_by_step == {"2": 50.0, "3": 50.0}


def test_coproduct_split_at_fixed_ratio():
    # The concrete case from docs/planning/07-schema-gap-review.md: step 1 splits its single
    # input into two named co-products (1-1 at 60%, 1-2 at 40%), routed to different next steps.
    graph = {
        "nodes": [
            _node("1", outputs=[
                {"output_item_id": "ITEM-1-1", "output_ratio": 0.6, "unit": "kg"},
                {"output_item_id": "ITEM-1-2", "output_ratio": 0.4, "unit": "kg"},
            ]),
            _node("2"),
            _node("3"),
        ],
        "transitions": [
            _transition("1", "2", output_item_id="ITEM-1-1"),
            _transition("1", "3", output_item_id="ITEM-1-2"),
        ],
        "resource_bindings": [
            _resource_binding("1", "R1", 1),
            _resource_binding("2", "R2", 1),
            _resource_binding("3", "R3", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0),
            _proc("2", std_time_per=1.0),
            _proc("3", std_time_per=1.0),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "2", "capacity": None},
            {"step_no": "3", "capacity": None},
        ],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    exits_by_step = {}
    for e in result["event_log"]:
        if e["event_type"] == "exit":
            exits_by_step[e["step_no"]] = exits_by_step.get(e["step_no"], 0) + e["qty"]
    assert exits_by_step == {"2": 60.0, "3": 40.0}


def test_merge_step_consumes_one_to_one_from_each_predecessor():
    graph = {
        "nodes": [
            _node("1"),
            _node("2"),
            _node("3", flow_type="merge"),
        ],
        "transitions": [
            _transition("1", "3"),
            _transition("2", "3"),
        ],
        "resource_bindings": [
            _resource_binding("1", "R1", 1),
            _resource_binding("2", "R2", 1),
            _resource_binding("3", "R3", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0),
            _proc("2", std_time_per=1.0),
            _proc("3", std_time_per=1.0),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "2", "capacity": None},
            {"step_no": "3", "capacity": None},
        ],
    }
    inbound_plans = [
        _inbound_plan("PLAN-1", "ITEM-IN-1", 10),
        _inbound_plan("PLAN-2", "ITEM-IN-2", 10),
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    exit_qty = sum(e["qty"] for e in result["event_log"] if e["event_type"] == "exit")
    assert exit_qty == 10  # 10 units from each branch, combined 1:1 into 10 merged units


def test_merge_step_consumes_asymmetric_bom_ratio():
    # 2:1 BOM: merge step 3 needs 2 units from step 1 for every 1 unit from step 2.
    # Step 1's supply (14) is the binding constraint at that ratio: 14/2 = 7 cycles,
    # vs. step 2's 100/1 = 100 cycles. A naive 1:1 assumption would predict min(14, 100)
    # = 14 -- getting 7 instead proves the 2:1 ratio is actually being applied.
    graph = {
        "nodes": [
            _node("1"),
            _node("2"),
            _node("3", flow_type="merge"),
        ],
        "transitions": [
            _transition("1", "3", consumption_ratio=2),
            _transition("2", "3", consumption_ratio=1),
        ],
        "resource_bindings": [
            _resource_binding("1", "R1", 1),
            _resource_binding("2", "R2", 1),
            _resource_binding("3", "R3", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0),
            _proc("2", std_time_per=1.0),
            _proc("3", std_time_per=1.0),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "2", "capacity": None},
            {"step_no": "3", "capacity": None},
        ],
    }
    inbound_plans = [
        _inbound_plan("PLAN-1", "ITEM-IN-1", 14),
        _inbound_plan("PLAN-2", "ITEM-IN-2", 100),
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    exit_qty = sum(e["qty"] for e in result["event_log"] if e["event_type"] == "exit")
    assert exit_qty == 7


def test_terminal_step_with_two_outputs_logs_two_exit_events():
    graph = {
        "nodes": [
            _node("1", outputs=[
                {"output_item_id": "MAIN", "output_ratio": 0.9, "unit": None},
                {"output_item_id": "SCRAP", "output_ratio": 0.1, "unit": None},
            ]),
        ],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    exits = {e["item_id"]: e["qty"] for e in result["event_log"] if e["event_type"] == "exit"}
    assert exits == {"MAIN": 90.0, "SCRAP": 10.0}


def test_input_qty_per_scales_consumption_from_container():
    # docs/planning/07-schema-gap-review.md 3-3: Recipe.length_factor.input_per_output (or a
    # step's own input_qty_per) means "N units of input per 1 unit of output" -- e.g. cable
    # drawing consumes more raw length than the finished length it produces. With
    # input_qty_per=2.0 and a 100-unit supply, only 50 output units can be produced
    # (2 consumed per output, 100/2 = 50), all consumed in a single chunk (well under
    # CHUNK_QTY_CAP) so there's no leftover.
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0, input_qty_per=2.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["throughput_total"] == 50
    process_events = [e for e in result["event_log"] if e["event_type"] == "process"]
    assert [e["qty"] for e in process_events] == [50]


def test_input_qty_per_scales_batch_consumption():
    graph = {
        "nodes": [_node("1", production_type="batch", batch_size=10)],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0, input_qty_per=2.0)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    # Exactly enough for one batch (10 output units * 2 input-per-output = 20 consumed).
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 20)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["throughput_total"] == 10


def test_loss_rate_reduces_yield_but_not_processing_time():
    # loss_rate=0.1 means 10% of processed qty is scrapped before reaching downstream/exit,
    # but the resource still spends time on the full (pre-loss) qty it pulled and processed.
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0, loss_rate=0.1)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["throughput_total"] == 90.0
    process_events = [e for e in result["event_log"] if e["event_type"] == "process"]
    assert [e["qty"] for e in process_events] == [100]  # full qty processed, time charged on it
    loss_events = [e for e in result["event_log"] if e["event_type"] == "loss"]
    assert [e["qty"] for e in loss_events] == [10.0]
    # 100 min to process the 100-unit chunk: resource was busy the full time regardless of loss.
    assert result["summary"]["resource_utilization"]["R1"] == 100 / 1440


def test_input_qty_per_and_loss_rate_combine_with_recipe_selection_from_compiler():
    # End-to-end sanity check that compiler.py's resolved_input_qty_per/loss_rate flow
    # straight through to the simulator unchanged (both apply independently: consumption
    # scaling on the way in, yield loss on the way out).
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0, input_qty_per=2.0, loss_rate=0.1)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    # 100 input / 2 per output = 50 units processed, then 10% loss -> 45 exit.
    assert result["summary"]["throughput_total"] == 45.0


def test_setup_time_charged_once_when_step_never_changes_on_its_resource():
    # docs/planning/07-schema-gap-review.md 3-4: a step with sole use of its equipment_group
    # never sees the resource's "last processed step" change away from itself, so setup_time
    # is still charged only on the very first cycle -- old behavior, now derived from the
    # changeover rule rather than a separate "first cycle only" flag.
    graph = {
        "nodes": [_node("1")],
        "transitions": [],
        "resource_bindings": [_resource_binding("1", "R1", 1)],
        "processing_time_plan": [_proc("1", std_time_per=1.0, setup_time=5)],
        "queue_plan": [{"step_no": "1", "capacity": None}],
    }
    inbound_plans = [_inbound_plan("PLAN-1", "ITEM-IN-1", 100_000)]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    # Cycle 1: 500 qty * 1.0 + 5 setup = 505min, ends at t=505.
    # Cycle 2: same step, resource identity unchanged -> no setup: 500 * 1.0 = 500min, ends at t=1005.
    # Cycle 3 would end at 1005 + 505 (with no setup would be 500) > 1440 -- never completes.
    process_events = [e for e in result["event_log"] if e["event_type"] == "process"]
    assert [e["qty"] for e in process_events] == [500, 500]
    setup_events = [e for e in result["event_log"] if e["event_type"] == "setup"]
    assert len(setup_events) == 1
    assert setup_events[0]["qty"] == 5  # qty carries the setup/changeover duration here
    assert result["summary"]["throughput_total"] == 1000


def test_setup_time_repeats_on_every_changeover_between_steps_sharing_a_resource():
    # Step "0" (no resource) delays step "2"'s supply until well after step "1" has already
    # finished on the shared resource and gone idle waiting for more input that never
    # arrives -- so step "1" is guaranteed to acquire R-SHARED first, and step "2" is
    # guaranteed to acquire it only after step "1" fully releases it. That makes the
    # resource's last-identity switch from "1" to "2" deterministic:
    #   step 1: qty=10, std_time_per=1.0, setup_time=5 -> first-ever use of R-SHARED
    #     (changeover from None) -> proc_time = 10*1 + 5 = 15, runs t=[0, 15).
    #   step 0: qty=5, std_time_per=1.0, no resource -> proc_time = 5, runs t=[0, 5),
    #     hands 5 units to step "2" at t=5 (step "2" then queues for R-SHARED until t=15).
    #   step 2: qty=5, std_time_per=1.0, setup_time=7 -> changeover from "1" -> "2"
    #     -> proc_time = 5*1 + 7 = 12, runs t=[15, 27).
    graph = {
        "nodes": [
            _node("1"),
            _node("0"),
            _node("2"),
        ],
        "transitions": [_transition("0", "2")],
        "resource_bindings": [
            _resource_binding("1", "R-SHARED", 1),
            _resource_binding("2", "R-SHARED", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0, setup_time=5),
            _proc("0", std_time_per=1.0),
            _proc("2", std_time_per=1.0, setup_time=7),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "0", "capacity": None},
            {"step_no": "2", "capacity": None},
        ],
    }
    inbound_plans = [
        _inbound_plan("PLAN-1", "ITEM-IN-1", 10),
        _inbound_plan("PLAN-0", "ITEM-IN-0", 5),
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    process_events = {e["step_no"]: e for e in result["event_log"] if e["event_type"] == "process"}
    assert process_events["1"]["sim_time"] == 0
    assert process_events["2"]["sim_time"] == 15

    setup_events = {e["step_no"]: e for e in result["event_log"] if e["event_type"] == "setup"}
    assert setup_events["1"]["qty"] == 5  # changeover from no prior user of R-SHARED
    assert setup_events["2"]["qty"] == 7  # changeover from step "1" to step "2"

    assert result["summary"]["resource_utilization"]["R-SHARED"] == pytest.approx(27 / 1440)
    # Step "1" is also terminal (no outgoing transition), so it exits its own 10 units too.
    assert result["summary"]["exit_qty_by_step"] == {"1": 10.0, "2": 5.0}


def test_shared_resource_serializes_contending_steps():
    # Steps 1 and 2 share resource R1 (capacity 1): they cannot both process at once,
    # so combined busy time can't exceed the simulation duration.
    graph = {
        "nodes": [_node("1"), _node("2")],
        "transitions": [],
        "resource_bindings": [
            _resource_binding("1", "R1", 1),
            _resource_binding("2", "R1", 1),
        ],
        "processing_time_plan": [
            _proc("1", std_time_per=1.0),
            _proc("2", std_time_per=1.0),
        ],
        "queue_plan": [
            {"step_no": "1", "capacity": None},
            {"step_no": "2", "capacity": None},
        ],
    }
    inbound_plans = [
        _inbound_plan("PLAN-1", "ITEM-IN-1", 100_000),
        _inbound_plan("PLAN-2", "ITEM-IN-2", 100_000),
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["resource_utilization"]["R1"] <= 1.0
    # Both steps contend for R1, so neither alone can reach the ~1000-unit throughput
    # the single-step test achieved with the same resource all to itself.
    assert result["summary"]["throughput_total"] < 2000
