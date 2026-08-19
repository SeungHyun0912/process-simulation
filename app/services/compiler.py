"""ProcessRouting -> compiled_graph_object, per docs/schema/simpy-schema-compiler.json
(COMPILER_MAPPING_RULE) and docs/example/compiled_graph_object_example.

Routing-level gates (dangling refs, missing equipment master, incomplete graph) are
checked by app.services.routing_validation.build_validation_report. This module adds
the compile-only gate (unresolved processing time) on top, since a routing may be
published before every step's timing is resolved but must not be compiled that way.
"""

from sqlalchemy.orm import Session

from app.models.equipment import Equipment, EquipmentGroup
from app.models.location import Location
from app.models.process_routing import ProcessRouting, ProcessStep
from app.models.product import Product
from app.models.runtime_profile import RuntimeProfile
from app.services.routing_validation import _link_entry_terminal_steps, build_validation_report

DEFAULT_RUNTIME_ECHO = {
    "time_unit": "day",
    "base_time_granularity": "minute",
    "duration_days": 30,
    "warmup_period": 0,
    "replication_count": 1,
    "random_seed": 42,
    "speed_mode": "fixed",
    "deterministic_mode": True,
    "enable_breakdown": False,
    "enable_preventive_maintenance": False,
    "enable_defect_generation": False,
    "enable_rework_flow": False,
    "enable_shift_calendar": False,
}


def _runtime_echo(runtime_profile: RuntimeProfile | None) -> dict:
    if runtime_profile is None:
        return dict(DEFAULT_RUNTIME_ECHO)
    return {
        **runtime_profile.time_control,
        **runtime_profile.execution_mode,
        **runtime_profile.scenario_toggles,
    }


def _transition_type(from_step: ProcessStep, to_step_no: str, steps_by_no: dict[str, ProcessStep]) -> str:
    """A fork point's own flow_type is typically "sequential" -- it's the branch targets that are
    marked "parallel". So a fan-out is detected from the *target*'s flow_type plus the source
    having more than one outgoing transition, not from the source step's own flow_type.
    """
    to_step = steps_by_no.get(to_step_no)
    if to_step is not None and to_step.flow_type == "merge":
        return "merge_input"
    if to_step is not None and to_step.flow_type == "parallel" and len(from_step.next_steps) > 1:
        return "parallel_split"
    return "sequential"


def compile_routing(routing: ProcessRouting, runtime_profile: RuntimeProfile | None, db: Session) -> dict:
    """Return {"status": "success"|"blocked", "compiled_graph_object": dict|None, "validation_report": dict}."""
    report = build_validation_report(routing, db)
    blocking_errors = list(report["blocking_errors"])

    for step in routing.steps:
        if step.std_time_per is None:
            blocking_errors.append(
                {
                    "rule_id": "BLOCK_UNRESOLVED_PROCESSING_TIME",
                    "path": f"steps[{step.step_no}].std_time_per",
                    "message": f"step {step.step_no} has no std_speed to derive a processing time from",
                }
            )

    combined_report = {**report, "blocking_errors": blocking_errors}

    if blocking_errors or report["graph_completeness_status"] in ("incomplete", "blocked"):
        return {"status": "blocked", "compiled_graph_object": None, "validation_report": combined_report}

    links = routing.product_links
    products_by_id = {
        p.product_id: p
        for p in db.query(Product).filter(Product.product_id.in_([link.product_id for link in links])).all()
    }
    steps_by_no = {s.step_no: s for s in routing.steps}

    nodes = []
    transitions = []
    resource_bindings = []
    processing_time_plan = []
    queue_plan = []
    parallel_group_ids = set()
    has_merge = False

    for step in routing.steps:
        nodes.append(
            {
                "node_id": f"STEP-{step.step_no}",
                "step_no": step.step_no,
                "node_type": "process_step",
                "process_id": step.process_id,
                "process_group_id": step.process_group_id,
                "process_name": step.process_name,
                "input_item_id": step.input_item_id,
                "outputs": [
                    {"output_item_id": o.output_item_id, "output_ratio": o.output_ratio, "unit": o.unit}
                    for o in step.outputs
                ],
                "production_type": step.production_type,
                "flow_type": step.flow_type,
                "parallel_group_id": step.parallel_group_id or None,
                "join_condition": step.join_condition or None,
                "batch_size": step.batch_size,
                "batch_unit": step.batch_unit,
                "input_location_id": step.input_location_id,
                "output_location_id": step.output_location_id,
                "inbound_route_id": step.inbound_route_id,
                "schema_status": step.schema_status,
                "reference_status": step.reference_status,
                "process_specific": step.process_specific,
            }
        )

        if step.parallel_group_id:
            parallel_group_ids.add(step.parallel_group_id)
        if step.flow_type == "merge":
            has_merge = True

        for transition in step.next_steps:
            transitions.append(
                {
                    "transition_id": f"TR-{step.step_no}-{transition.to_step_no}",
                    "from_step_no": step.step_no,
                    "to_step_no": transition.to_step_no,
                    "transition_type": _transition_type(step, transition.to_step_no, steps_by_no),
                    "condition": transition.condition,
                    "interpreted_condition": transition.interpreted_condition,
                    "parallel_group_id": step.parallel_group_id or None,
                    "output_item_id": transition.output_item_id,
                    "consumption_ratio": transition.consumption_ratio,
                }
            )

        if step.equipment_group:
            group = db.query(EquipmentGroup).filter_by(group_id=step.equipment_group).one_or_none()
            members = db.query(Equipment).filter_by(group_id=step.equipment_group).all()
            resource_bindings.append(
                {
                    "step_no": step.step_no,
                    "resource_key": step.equipment_group,
                    "resource_type": "simpy.Resource",
                    "resolved_resource_id": members[0].equipment_id if len(members) == 1 else None,
                    "capacity": group.capacity if (group and group.capacity) else 1,
                    "capacity_source": "master_data" if (group and group.capacity) else "default_resource_capacity",
                }
            )

        processing_time_plan.append(
            {
                "step_no": step.step_no,
                "processing_time_source": "derived_from_std_speed",
                "std_speed": step.std_speed,
                "std_time_per": step.std_time_per,
                "formula_id": "inverse_of_std_speed",
                "time_unit": "min_per_batch" if step.production_type == "batch" else "min_per_unit",
                "setup_time": step.setup_time or 0,
            }
        )

        input_location = (
            db.query(Location).filter_by(location_id=step.input_location_id).one_or_none()
            if step.input_location_id
            else None
        )
        queue_entry = {
            "queue_id": f"Q::{routing.product_id}::{step.step_no}",
            "step_no": step.step_no,
            "queue_discipline": "FIFO",
            "capacity": input_location.storage_capacity if input_location else None,
            "capacity_policy": "unbounded_if_missing",
            "wip_tracking_enabled": True,
        }
        if step.flow_type == "merge":
            queue_entry["merge_policy"] = "wait_for_all_required_inputs"
        queue_plan.append(queue_entry)

    product_contexts = []
    for link in links:
        product = products_by_id[link.product_id]
        entry_steps, terminal_steps = _link_entry_terminal_steps(routing, link)
        product_contexts.append(
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "unit": product.unit,
                "entry_step_nos": entry_steps,
                "terminal_step_nos": terminal_steps,
                "is_primary": link.is_primary,
            }
        )

    compiled_graph_object = {
        "compile_target": "simpy",
        "product_contexts": product_contexts,
        "graph_summary": {
            "graph_id": f"GRAPH-{routing.product_id}-{routing.version}",
            "graph_completeness_status": report["graph_completeness_status"],
            "node_count": len(nodes),
            "transition_count": len(transitions),
            "has_parallel_branch": bool(parallel_group_ids),
            "has_merge": has_merge,
            "linked_product_ids": [link.product_id for link in links],
        },
        "nodes": nodes,
        "transitions": transitions,
        "resource_bindings": resource_bindings,
        "processing_time_plan": processing_time_plan,
        "queue_plan": queue_plan,
        "validation_report": combined_report,
        "runtime_echo": _runtime_echo(runtime_profile),
    }

    return {"status": "success", "compiled_graph_object": compiled_graph_object, "validation_report": combined_report}
