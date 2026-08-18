from app.services.simulation import run_simulation

TIME_CONTROL_1_DAY = {"duration_days": 1}  # 1440 minutes
OUTPUT_CONTROL = {"collect_wip_snapshot": True, "snapshot_interval": 60, "snapshot_interval_unit": "minute"}


def _node(step_no, flow_type="sequential", production_type="continuous", batch_size=None, batch_unit=None):
    return {
        "step_no": step_no,
        "flow_type": flow_type,
        "production_type": production_type,
        "batch_size": batch_size,
        "batch_unit": batch_unit,
        "input_item_id": f"ITEM-IN-{step_no}",
        "output_item_id": f"ITEM-OUT-{step_no}",
        "input_location_id": None,
    }


def _proc(step_no, std_time_per, setup_time=0):
    return {"step_no": step_no, "std_time_per": std_time_per, "setup_time": setup_time}


def _resource_binding(step_no, resource_key, capacity):
    return {"step_no": step_no, "resource_key": resource_key, "capacity": capacity}


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
    inbound_plans = [
        {
            "plan_id": "PLAN-1",
            "item_id": "ITEM-IN-1",
            "location_id": None,
            "inbound_qty": 100_000,
            "interval_value": 1,
            "interval_unit": "day",
        }
    ]

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
    inbound_plans = [
        {
            "plan_id": "PLAN-1",
            "item_id": "ITEM-IN-1",
            "location_id": None,
            "inbound_qty": 100_000,
            "interval_value": 1,
            "interval_unit": "day",
        }
    ]

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
            {"from_step_no": "1", "to_step_no": "2"},
            {"from_step_no": "1", "to_step_no": "3"},
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
        {
            "plan_id": "PLAN-1",
            "item_id": "ITEM-IN-1",
            "location_id": None,
            "inbound_qty": 100,
            "interval_value": 1,
            "interval_unit": "day",
        }
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    # Step 1 processes 100 units (all available on the one inbound delivery), splits 50/50.
    exits_by_step = {}
    for e in result["event_log"]:
        if e["event_type"] == "exit":
            exits_by_step[e["step_no"]] = exits_by_step.get(e["step_no"], 0) + e["qty"]
    assert exits_by_step == {"2": 50.0, "3": 50.0}


def test_merge_step_consumes_one_to_one_from_each_predecessor():
    graph = {
        "nodes": [
            _node("1"),
            _node("2"),
            _node("3", flow_type="merge"),
        ],
        "transitions": [
            {"from_step_no": "1", "to_step_no": "3"},
            {"from_step_no": "2", "to_step_no": "3"},
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
        {
            "plan_id": "PLAN-1",
            "item_id": "ITEM-IN-1",
            "location_id": None,
            "inbound_qty": 10,
            "interval_value": 1,
            "interval_unit": "day",
        },
        {
            "plan_id": "PLAN-2",
            "item_id": "ITEM-IN-2",
            "location_id": None,
            "inbound_qty": 10,
            "interval_value": 1,
            "interval_unit": "day",
        },
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    exit_qty = sum(e["qty"] for e in result["event_log"] if e["event_type"] == "exit")
    assert exit_qty == 10  # 10 units from each branch, combined 1:1 into 10 merged units


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
        {
            "plan_id": "PLAN-1",
            "item_id": "ITEM-IN-1",
            "location_id": None,
            "inbound_qty": 100_000,
            "interval_value": 1,
            "interval_unit": "day",
        },
        {
            "plan_id": "PLAN-2",
            "item_id": "ITEM-IN-2",
            "location_id": None,
            "inbound_qty": 100_000,
            "interval_value": 1,
            "interval_unit": "day",
        },
    ]

    result = run_simulation(graph, TIME_CONTROL_1_DAY, OUTPUT_CONTROL, inbound_plans)

    assert result["summary"]["resource_utilization"]["R1"] <= 1.0
    # Both steps contend for R1, so neither alone can reach the ~1000-unit throughput
    # the single-step test achieved with the same resource all to itself.
    assert result["summary"]["throughput_total"] < 2000
