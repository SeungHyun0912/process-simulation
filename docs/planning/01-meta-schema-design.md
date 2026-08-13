# 01. Meta Schema 설계 — SimPy Input 표준화

대응 요구사항: **(1) 여러 공정 정보를 높은 수준에서 Integration 하는 Meta Schema 구조 적립**

## 1. 목표

현재 `COMMON_FIELD_DICTIONARY` + `FIELD_META_REGISTRY`(`docs/schema/process-schema.json`)는 아래 정보만 표준화되어 있다.

- 제품(product), 케이블 설계(conductor/insulation/sheath)
- 공정 라우팅 스텝(step_no, process_id, input/output item, std_speed, std_time_per, flow_type, next_steps)
- 설비 그룹(equipment_group), 레시피(recipe)

사용자가 요청한 항목 중 **아직 표준화되지 않은 부분**은:

1. **자재 위치(Material Location)** — 원자재/반제품/완제품이 물리적으로 어디 있는지 (창고, 라인 버퍼, 공정 투입점)
2. **이동 경로 및 소요 시간(Transport/Move)** — 위치 A → 위치 B 이동에 걸리는 시간/거리/운송 수단
3. 공정별 원자재/반제품, 공정 시간은 이미 존재 (input_item_id/output_item_id/std_speed/std_time_per) → **확장 불필요, 그대로 재사용**

따라서 이 문서는 기존 `COMMON_FIELD_DICTIONARY`를 **확장**하는 형태로 설계한다 (교체 아님).

## 2. 확장 원칙 (기존 설계 원칙 계승)

기존 `_meta.design_principles`를 그대로 따른다:

- `path_aware_first`: 필드는 canonical_key만이 아니라 실제 JSON 경로(path_patterns)를 갖는다.
- `provisional_first_for_new_fields`: 신규 필드는 `schema_status: "provisional"`로 시작, 검증 후 `official` 승격.
- `source_vs_derived_separation`: 원시값(raw)과 파생값(derived)을 구분 (예: std_time_per는 std_speed에서 파생).
- `simpy_compile_oriented`: 필드 설계는 "SimPy로 컴파일 가능한가"를 기준으로 한다.

## 3. 신규 Common Field 제안

`COMMON_FIELD_DICTIONARY.fields`에 추가할 항목 (기존 `CF_*` 네이밍 규칙 유지):

| 필드 ID | canonical_key | 설명(ko) | 타입 | enum/비고 |
|---|---|---|---|---|
| `CF_LOCATION_ID` | `location_id` | 위치 식별자 | string | — |
| `CF_LOCATION_TYPE` | `location_type` | 위치 유형 | string | `warehouse`, `line_buffer`, `process_input`, `process_output`, `staging` |
| `CF_LOCATION_NAME` | `location_name` | 위치명 | string | — |
| `CF_ROUTE_ID` | `route_id` | 이동 경로 식별자 | string | — |
| `CF_FROM_LOCATION_ID` | `from_location_id` | 출발 위치 | string | → `CF_LOCATION_ID` 참조 |
| `CF_TO_LOCATION_ID` | `to_location_id` | 도착 위치 | string | → `CF_LOCATION_ID` 참조 |
| `CF_TRANSPORT_MODE` | `transport_mode` | 운송 수단 | string | `forklift`, `agv`, `conveyor`, `manual`, `crane` |
| `CF_TRANSPORT_DISTANCE` | `transport_distance` | 이동 거리 | number | `unit_family: length` |
| `CF_TRANSPORT_TIME` | `transport_time` | 이동 소요 시간 | number | `unit_family: time`, `value_role: raw` (또는 거리/속도로부터 derived) |
| `CF_TRANSPORT_SPEED` | `transport_speed` | 운송 수단 속도 | number | `unit_family: speed`, 있으면 transport_time을 derived로 전환 |
| `CF_TRANSPORT_CAPACITY` | `transport_capacity_per_trip` | 1회 이동 가능 수량 | number | 배치 이동(예: 파렛트 단위) 지원 |
| `CF_STORAGE_CAPACITY` | `storage_capacity` | 위치 최대 저장 용량 | number | 창고/버퍼 큐 capacity 산정에 사용 |
| `CF_STOCK_ITEM_ID` | `item_id` | 재고/품목 식별자 | string | 기존 `input_item_id`/`output_item_id`와 동일 도메인 |
| `CF_STOCK_QTY` | `stock_qty` | 현재 재고량 | number | 시뮬레이션 초기 상태(initial WIP)에 사용 |

`std_time_per`처럼, `transport_time`도 `transport_distance / transport_speed`로 **파생 가능**하도록 `formula_id: "inverse_of... "` 대신 신규 `formula_id: "distance_over_speed"`를 정의한다 (`derived_from: [transport_distance, transport_speed]`).

## 4. 신규 엔티티(Entity Scope) 및 경로

기존 `process_routings[]`, `products[]`, `equipments[]`, `recipes[]`와 병렬로 최상위 엔티티를 추가한다.

```
locations[]                     # 위치 마스터 (창고/라인버퍼/투입점 등)
  .location_id
  .location_type
  .location_name
  .storage_capacity

transport_routes[]              # 이동 경로 마스터
  .route_id
  .from_location_id
  .to_location_id
  .transport_mode
  .transport_distance
  .transport_speed
  .transport_time              # derived (있으면 raw 우선)
  .transport_capacity_per_trip

process_routings[].steps[].logistics     # 스텝 단위 위치 바인딩 (신규 하위 객체)
  .input_location_id            # 이 스텝이 원자재를 가져오는 위치
  .output_location_id           # 이 스텝의 산출물이 놓이는 위치
  .inbound_route_id             # input_location_id로 오는 경로 (transport_routes 참조)

inventory_snapshots[]           # 초기 재고/WIP (시뮬레이션 시작 시점 상태, 선택)
  .location_id
  .item_id
  .stock_qty
  .snapshot_at
```

`FIELD_META_REGISTRY.entries`에는 위 경로마다 `FM_LOCATION_*`, `FM_ROUTE_*`, `FM_ROUTING_LOGISTICS_*` 항목을 동일한 포맷(common_field_id, path_patterns, entity_scope, editable, value_role, schema_status)으로 추가한다. 기존 `FM_ROUTING_EQUIPMENT_GROUP`이 `reference_target_paths: ["equipments[].group_id"]`를 갖듯, `FM_ROUTING_LOGISTICS_INPUT_LOCATION`도 `reference_target_paths: ["locations[].location_id"]`를 갖는다.

## 5. 도메인별 확장 패턴 재사용

기존 `process_specific.{drawing, stranding, extrusion, cabling, sheathing}` 패턴(케이블 공정 전용 필드)을 그대로 물류에도 적용:

- `logistics_specific.{warehouse, agv_fleet, conveyor}` 같은 형태로, 공정 도메인이 늘어나도(예: 화학, 조립) 핵심 스키마를 건드리지 않고 확장 가능하게 한다.
- 신규 도메인 필드는 항상 `schema_status: "provisional"`로 시작 → 실사용 검증 후 `official`.

## 6. PROCESS_DEFINITION_INTENT 템플릿 반영

`PROCESS_DEFINITION_INTENT.template`에 다음을 추가:

```jsonc
"normalized_entities": {
  "items": [],
  "materials": [],
  "equipment_groups": [],
  "process_ids": [],
  "process_group_ids": [],
  "locations": [],          // 신규
  "transport_routes": []    // 신규
},
"process_graph": {
  "steps": [{
    // ...기존 필드...
    "logistics": {          // 신규 하위 객체
      "input_location_id": null,
      "output_location_id": null,
      "inbound_route_id": null
    }
  }]
}
```

`validation_report`에도 `unresolved_reference_paths`가 `locations[].location_id`, `transport_routes[].route_id`까지 검사하도록 확장.

## 7. 컴파일러(`COMPILER_MAPPING_RULE`) 영향

- `queue_binding` 개념을 스텝 큐에서 **위치(location) 큐**로도 확장 가능 (창고 저장 capacity = SimPy `Store`/`Container` capacity).
- `resource_resolution_rules`와 동일한 패턴으로 `transport_resolution_rules`를 추가: `transport_mode` → SimPy `Resource`(운송 수단 대수 제한) 매핑.
- 새 블로킹 규칙 후보: `BLOCK_MISSING_LOCATION_MASTER`, `BLOCK_MISSING_ROUTE_MASTER` (기존 `BLOCK_MISSING_RESOURCE_MASTER`와 동일 심각도 `critical`).

이 부분은 [`02-process-management.md`](./02-process-management.md)와 컴파일러 구현 단계(P2, [`00-overview.md`](./00-overview.md) 로드맵)에서 코드로 옮긴다.

## 8. 버전 관리

- `_meta.schema_version`을 `0.1.0-draft` → `0.2.0-draft`로 올리고, 변경 로그(`CHANGELOG`)에 "위치/이동 경로 필드 추가"를 기록.
- 하위 호환: 기존 필드는 변경하지 않음 (추가만). 기존 `compiled_graph_object` 예시는 `logistics` 없이도 여전히 유효해야 한다 (신규 필드는 optional).

## 9. 미해결 질문

- 위치의 계층 구조(사이트 > 구역 > 라인 > 버퍼)가 필요한가, 아니면 flat한 `location_id`로 충분한가?
- 이동 경로가 방향성이 있는지(A→B와 B→A가 다른 소요시간) — 현재 설계는 방향성 있음(`from`/`to` 별도)으로 가정.
- `transport_time`을 고정값(deterministic)으로 시작할지, `SIMPY_RUNTIME_META.stochastic_defaults`처럼 분포(distribution)를 지원할지 — 1차 구현은 고정값, 추후 확장.
