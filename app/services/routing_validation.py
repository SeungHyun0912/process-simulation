"""Routing-level validation gates shared by the /validate, /publish, and compile-run flows.

Mirrors the graph_validation_rules in docs/schema/simpy-schema-compiler.json
(COMPILER_MAPPING_RULE). Compile-time-only gates (e.g. unresolved processing time)
live in app/services/compiler.py instead, since a routing may legitimately be
published before every step's timing is resolved.
"""

from sqlalchemy.orm import Session

from app.models.equipment import EquipmentGroup
from app.models.process_routing import ProcessRouting, RoutingProductLink


def _live_entry_terminal_steps(routing: ProcessRouting) -> tuple[list[str], list[str]]:
    """Steps with no incoming transition (entry) / no outgoing transition (terminal).

    Used for a routing's primary RoutingProductLink, whose entry/terminal steps are never
    stored -- they can't be known at routing-creation time (zero steps exist yet) and are
    always recomputed from the graph's actual topology instead.
    """
    step_nos = {s.step_no for s in routing.steps}
    targets = {t.to_step_no for step in routing.steps for t in step.next_steps}
    sources = {step.step_no for step in routing.steps if step.next_steps}
    entry_steps = [s for s in step_nos if s not in targets]
    terminal_steps = [s for s in step_nos if s not in sources]
    return entry_steps, terminal_steps


def _link_entry_terminal_steps(routing: ProcessRouting, link: RoutingProductLink) -> tuple[list[str], list[str]]:
    """Entry/terminal steps for one product's view of the routing: live-computed for the
    primary link (see _live_entry_terminal_steps), or the fork's own stored boundaries."""
    if link.is_primary:
        return _live_entry_terminal_steps(routing)
    return list(link.entry_step_nos or []), list(link.terminal_step_nos or [])


def extract_product_subgraph(routing: ProcessRouting, link: RoutingProductLink) -> set[str]:
    """Step_nos reachable backward from link's terminal steps, stopping at its entry steps."""
    entry_steps, terminal_steps = _link_entry_terminal_steps(routing, link)
    entry_set = set(entry_steps)

    predecessors: dict[str, list[str]] = {s.step_no: [] for s in routing.steps}
    for step in routing.steps:
        for transition in step.next_steps:
            predecessors.setdefault(transition.to_step_no, []).append(step.step_no)

    visited: set[str] = set()
    queue = list(terminal_steps)
    while queue:
        step_no = queue.pop()
        if step_no in visited:
            continue
        visited.add(step_no)
        if step_no in entry_set:
            continue
        queue.extend(predecessors.get(step_no, []))
    return visited


def build_validation_report(routing: ProcessRouting, db: Session) -> dict:
    """Run every graph_validation_rule (module docstring) against one routing's current steps,
    updating each step's reference_status and the routing's graph_completeness_status as a
    side effect. Returns the shared report shape consumed by /validate, /publish, and compile."""
    steps = routing.steps
    step_nos = {s.step_no for s in steps}
    blocking_errors = []
    warnings = []

    if not steps:
        blocking_errors.append(
            {"rule_id": "BLOCK_GRAPH_INCOMPLETE", "path": "steps", "message": "routing has no steps"}
        )

    for step in steps:
        # A step must declare at least one output item -- otherwise there's nothing for a
        # transition or the compiler to route/split downstream.
        if not step.outputs:
            blocking_errors.append(
                {
                    "rule_id": "BLOCK_STEP_HAS_NO_OUTPUT",
                    "path": f"steps[{step.step_no}].outputs",
                    "message": f"step {step.step_no} has no declared output items",
                }
            )
        else:
            output_item_ids = {o.output_item_id for o in step.outputs}
            # Ratios not summing to 1.0 is only a warning, not a block: scrap/loss or an
            # intentional yield increase can legitimately push the sum away from 1.0.
            ratio_sum = sum(o.output_ratio for o in step.outputs)
            if abs(ratio_sum - 1.0) > 1e-6:
                warnings.append(
                    {
                        "rule_id": "WARN_OUTPUT_RATIO_SUM",
                        "path": f"steps[{step.step_no}].outputs",
                        "message": f"step {step.step_no} output_ratio sums to {ratio_sum}, not 1.0",
                    }
                )

        for transition in step.next_steps:
            if transition.to_step_no not in step_nos:
                blocking_errors.append(
                    {
                        "rule_id": "BLOCK_DANGLING_NEXT_STEP",
                        "path": f"steps[{step.step_no}].next_steps",
                        "message": (
                            f"{step.step_no} -> {transition.to_step_no} but step "
                            f"{transition.to_step_no} is missing"
                        ),
                    }
                )

            if step.outputs:
                # A co-product step (more than one declared output) needs every outgoing
                # transition to say which output item it carries -- otherwise the compiler/
                # simulator can't tell which of the step's outputs feeds which successor.
                if transition.output_item_id is None and len(step.outputs) > 1:
                    blocking_errors.append(
                        {
                            "rule_id": "BLOCK_TRANSITION_OUTPUT_ITEM_UNKNOWN",
                            "path": f"steps[{step.step_no}].next_steps",
                            "message": (
                                f"step {step.step_no} has {len(step.outputs)} outputs; the transition "
                                f"to {transition.to_step_no} must specify which output_item_id it carries"
                            ),
                        }
                    )
                elif transition.output_item_id is not None and transition.output_item_id not in output_item_ids:
                    blocking_errors.append(
                        {
                            "rule_id": "BLOCK_TRANSITION_OUTPUT_ITEM_UNKNOWN",
                            "path": f"steps[{step.step_no}].next_steps",
                            "message": (
                                f"transition {step.step_no} -> {transition.to_step_no} references output "
                                f"item {transition.output_item_id!r}, which step {step.step_no} doesn't produce"
                            ),
                        }
                    )

        # A step can reference an equipment_group before that master-data row exists (e.g.
        # during early/provisional authoring) -- that's a blocking error, but we still record
        # the resolution outcome on reference_status so the UI can show it either way.
        if step.equipment_group:
            resolved = (
                db.query(EquipmentGroup).filter_by(group_id=step.equipment_group).one_or_none()
                is not None
            )
            equipment_group_ref = "resolved" if resolved else "master_missing"
            if not resolved:
                blocking_errors.append(
                    {
                        "rule_id": "BLOCK_MISSING_RESOURCE_MASTER",
                        "path": f"steps[{step.step_no}].equipment_group",
                        "message": f"{step.equipment_group} is not resolved in equipment_group master",
                    }
                )
        else:
            equipment_group_ref = "provisional"

        step.reference_status = {"equipment_group_ref": equipment_group_ref}

        if step.schema_status == "provisional":
            warnings.append(
                {
                    "rule_id": "ALLOW_PROVISIONAL_STEP",
                    "path": f"steps[{step.step_no}]",
                    "message": f"step {step.step_no} is provisional",
                }
            )

    if steps:
        # NOTE: since a primary link's terminal set is always the routing's full live terminal
        # set (see _link_entry_terminal_steps), covered_terminals below always includes every
        # live terminal as long as the routing has its (always-present) primary link -- so this
        # gate can't currently fire in practice. It becomes meaningful once primary scoping is
        # refined to mean "whatever forks haven't explicitly claimed" rather than "everything";
        # left in place (rather than removed) so that refinement doesn't also require re-adding
        # the gate and its tests from scratch.
        covered_terminals: set[str] = set()
        for link in routing.product_links:
            entry_steps, terminal_steps = _link_entry_terminal_steps(routing, link)
            covered_terminals.update(terminal_steps)
            if not link.is_primary:
                for s in [*entry_steps, *terminal_steps]:
                    if s not in step_nos:
                        blocking_errors.append(
                            {
                                "rule_id": "BLOCK_UNRESOLVED_LINK_STEP",
                                "path": f"product_links[{link.product_id}]",
                                "message": f"{s!r} is not a step in this routing",
                            }
                        )

        _, live_terminal_steps = _live_entry_terminal_steps(routing)
        for step_no in live_terminal_steps:
            if step_no not in covered_terminals:
                blocking_errors.append(
                    {
                        "rule_id": "BLOCK_ORPHAN_TERMINAL_STEP",
                        "path": f"steps[{step_no}]",
                        "message": f"terminal step {step_no} isn't claimed by any linked product",
                    }
                )

    # Completeness is a coarse status derived from the checks above: no steps yet, blocked by
    # a hard error, still has provisional (unofficial) steps, or fully resolved.
    if not steps:
        completeness = "incomplete"
    elif blocking_errors:
        completeness = "blocked"
    elif any(s.schema_status == "provisional" for s in steps):
        completeness = "provisional"
    else:
        completeness = "complete"

    routing.graph_completeness_status = completeness
    return {
        "graph_completeness_status": completeness,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }
