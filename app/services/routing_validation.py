"""Routing-level validation gates shared by the /validate, /publish, and compile-run flows.

Mirrors the graph_validation_rules in docs/schema/simpy-schema-compiler.json
(COMPILER_MAPPING_RULE). Compile-time-only gates (e.g. unresolved processing time)
live in app/services/compiler.py instead, since a routing may legitimately be
published before every step's timing is resolved.
"""

from sqlalchemy.orm import Session

from app.models.equipment import EquipmentGroup
from app.models.process_routing import ProcessRouting


def build_validation_report(routing: ProcessRouting, db: Session) -> dict:
    steps = routing.steps
    step_nos = {s.step_no for s in steps}
    blocking_errors = []
    warnings = []

    if not steps:
        blocking_errors.append(
            {"rule_id": "BLOCK_GRAPH_INCOMPLETE", "path": "steps", "message": "routing has no steps"}
        )

    for step in steps:
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
