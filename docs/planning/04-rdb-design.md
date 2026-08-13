# 04. RDB 저장 설계

대응 요구사항: **(4) 공정 정보, Meta Schema, 프로세스 관리 등을 RDB로 저장**

## 1. DB 선택 (제안)

**PostgreSQL** 을 제안한다. 이유:

- Meta Schema는 "진화 중"(provisional-first)이라 완전한 정규화(fully relational)로는 스키마 변경 비용이 큼 → `JSONB` 컬럼으로 유연한 부분(`process_specific`, `logistics`, `validation_report`)을 수용하고, 조회/조인이 빈번한 핵심 식별자(product_id, step_no, process_id 등)는 일반 컬럼으로 분리하는 **하이브리드** 구조가 적합.
- `compiled_graph_object`, 시뮬레이션 결과 로그처럼 원래 JSON 문서인 산출물을 그대로 저장하기 용이.

## 2. 테이블 그룹

### 2-1. Meta Schema 레지스트리 (스키마 자체를 관리)

```
meta_common_field                 -- COMMON_FIELD_DICTIONARY.fields 1행 = 1 canonical field
  id (PK), common_field_code (CF_*), canonical_key, description_ko,
  canonical_type, value_role, schema_status, path_sensitive,
  enum_domain (JSONB, nullable), unit_family (nullable),
  derived_from (JSONB, nullable), formula_id (nullable),
  schema_version, created_at, updated_at

meta_field_mapping                -- FIELD_META_REGISTRY.entries 1행 = 1 경로 매핑
  id (PK), field_mapping_code (FM_*), common_field_id (FK -> meta_common_field, nullable),
  canonical_key, path_patterns (JSONB, string[]), entity_scope,
  canonical_type, editable, value_role, schema_status,
  enum_domain (JSONB, nullable), reference_target_paths (JSONB, nullable),
  schema_version, created_at, updated_at
```

이 두 테이블을 RDB로 관리하는 이유: 신규 필드 추가/변경을 **배포 없이 데이터로 관리**하고, 05번 문서의 API(`GET /meta-schema/fields`)로 프런트엔드가 동적 폼을 그릴 수 있게 하기 위함.

### 2-2. 마스터 데이터

```
product
  id (PK), product_id (UK), product_name, product_type, unit, status,
  cable_design (JSONB, nullable)  -- conductor/insulation/cabling/sheath 등 도메인 전용 세부구조
  created_at, updated_at

equipment_group
  id (PK), group_id (UK), group_name, capacity, default_capacity_source

equipment
  id (PK), equipment_id (UK), group_id (FK -> equipment_group.group_id),
  capacity, attributes (JSONB)

location                          -- 01 확장분
  id (PK), location_id (UK), location_type, location_name, storage_capacity

transport_route                   -- 01 확장분
  id (PK), route_id (UK), from_location_id (FK -> location.location_id),
  to_location_id (FK -> location.location_id), transport_mode,
  transport_distance, transport_speed, transport_time, transport_capacity_per_trip

recipe
  id (PK), recipe_id (UK), product_id (FK, nullable), process_id (nullable),
  process_group_id (nullable), recipe_scope, setup_time,
  speed (JSONB), length_factor (JSONB), cable_recipe (JSONB, domain-specific)
```

### 2-3. 프로세스(라우팅) — 02번 문서의 핵심 저장소

```
process_routing
  id (PK), product_id (FK -> product.product_id), version,
  status (draft/validated/published/compiled/archived),
  graph_completeness_status, is_active (bool),
  created_by, created_at, updated_by, updated_at
  UNIQUE(product_id, version)

process_step
  id (PK), routing_id (FK -> process_routing.id),
  step_no, process_id, process_group_id, process_name,
  input_item_id, output_item_id, input_qty_per,
  equipment_group, std_speed, std_time_per, setup_time,
  flow_type, parallel_group_id, join_condition, production_type,
  input_location_id (FK -> location.location_id, nullable),   -- 01 확장분
  output_location_id (FK -> location.location_id, nullable),  -- 01 확장분
  inbound_route_id (FK -> transport_route.route_id, nullable),-- 01 확장분
  batch_size, batch_unit (nullable),     -- 01 확장분, production_type=batch 스텝에서 사용. Recipe가 아니라
                                          -- 여기(스텝)에 두는 이유: 동일 설비도 제품/공정에 따라 배치가 달라질 수 있음
  process_specific (JSONB, nullable),   -- drawing/extrusion 등 도메인 세부
  schema_status, reference_status (JSONB)
  UNIQUE(routing_id, step_no)

process_step_transition
  id (PK), from_step_id (FK -> process_step.id),
  to_step_no, condition, interpreted_condition

material_inbound_plan                   -- 01 확장분: 원자재 투입(arrival) 모델
  id (PK), plan_id (UK), item_id, location_id (FK -> location.location_id),
  inbound_qty, inbound_unit, interval_value, interval_unit,
  schema_status
  -- 이 테이블이 시뮬레이션의 "원자재가 얼마나/얼마나 자주 들어오는가"를 정의하는 기본값(master).
  -- 특정 시뮬레이션 실행에서의 오버라이드는 simulation_run 쪽에서 처리 (below).
```

### 2-4. 업로드/Ingestion — 03번 문서

```
upload_job
  id (PK), source_type (xlsx/csv/json/array), original_filename,
  status (parsing/extracting/awaiting_review/completed/failed),
  requested_by, requested_at, completed_at, error_message (nullable)

upload_job_draft
  id (PK), upload_job_id (FK), draft_payload (JSONB)  -- PROCESS_DEFINITION_INTENT 형태 초안 전체

upload_field_mapping
  id (PK), upload_job_id (FK), raw_source (예: "Sheet1!B"), raw_header_text,
  mapped_common_field_id (FK -> meta_common_field, nullable),
  confidence, decided_by (llm/human), decided_at

upload_field_alias                 -- 학습된 매핑 사전 (재사용)
  id (PK), raw_header_text_normalized (UK), common_field_id (FK), hit_count, last_used_at
```

### 2-5. 컴파일/시뮬레이션 — 05번 문서와 연결

```
compile_run
  id (PK), routing_id (FK -> process_routing.id), routing_version,
  binding_meta_version, runtime_meta_id (FK, nullable),
  compiled_graph_object (JSONB),   -- compiled_graph_object_example과 동일 구조
  validation_report (JSONB),
  status (success/blocked), created_by, created_at

runtime_profile                     -- SIMPY_RUNTIME_META 인스턴스
  id (PK), profile_name, time_control (JSONB), execution_mode (JSONB),
  scenario_toggles (JSONB), policy_refs (JSONB), output_control (JSONB),
  created_by, created_at

simulation_run
  id (PK), compile_run_id (FK -> compile_run.id), runtime_profile_id (FK),
  status (queued/running/succeeded/failed), started_at, finished_at,
  random_seed, replication_count, error_message (nullable),
  material_inbound_overrides (JSONB, nullable)  -- material_inbound_plan 기본값을 이 실행에서만 덮어쓸 때 사용

simulation_result_summary
  id (PK), simulation_run_id (FK), throughput, avg_wip, avg_lead_time,
  resource_utilization (JSONB), bottleneck_step_no (nullable)

simulation_event_log                -- 대용량 예상 → 파티셔닝/보존기간 정책 필요
  id (PK), simulation_run_id (FK), sim_time, event_type, step_no,
  resource_key, item_id, payload (JSONB)
```

`simulation_event_log`는 재현당 수만~수백만 행이 될 수 있으므로, 1차 구현은 JSONB 원본을 통째로 object storage/파일로 두고 RDB에는 **요약 통계만** 저장하는 방식도 대안으로 고려 (아래 미해결 질문 참고).

### 2-6. 사용자/권한/감사 — 05번 문서

```
app_user
  id (PK), email (UK), display_name, role (viewer/editor/approver/admin)

audit_log
  id (PK), entity_type, entity_id, action (create/update/delete/publish),
  diff (JSONB), acted_by (FK -> app_user), acted_at
```

## 3. ERD 개요 (텍스트)

```
product 1───N process_routing 1───N process_step 1───N process_step_transition
   │                                     │
   │                                     ├──FK──▶ location (input/output)
   │                                     └──FK──▶ transport_route
   │
   └──N recipe

process_routing 1───N compile_run 1───N simulation_run 1───1 simulation_result_summary
                                                        └──N simulation_event_log

upload_job 1───N upload_job_draft
upload_job 1───N upload_field_mapping──▶ meta_common_field
upload_field_alias ──▶ meta_common_field

meta_common_field 1───N meta_field_mapping
```

## 4. 마이그레이션/ORM 제안

- Python 스택이면 **SQLAlchemy + Alembic**(마이그레이션) 조합을 제안. Pydantic 모델을 API 레이어(05번 문서) DTO로 별도 유지하고 ORM 모델과 분리 (스키마 변경이 API 계약을 자동으로 깨지 않도록).
- Meta Schema 원본(`docs/schema/*.json`)은 **seed 데이터**로 취급 — 최초 마이그레이션 시 `meta_common_field`/`meta_field_mapping` 테이블에 그대로 적재하는 시드 스크립트 작성.

## 5. 미해결 질문

- RDB 종류가 PostgreSQL이 아닌 사내 표준 DB(MSSQL/MySQL/Oracle)로 고정되어 있는지 확인 필요 — 위 설계는 JSONB 의존도가 있어 MSSQL/MySQL이면 `JSON` 컬럼 타입으로 대체(문법만 다름, 개념은 동일).
- `simulation_event_log`를 RDB에 그대로 쌓을지, 별도 저장(파일/오브젝트 스토리지 + RDB는 메타/요약만)으로 분리할지는 예상 시뮬레이션 규모(스텝 수 × 반복 횟수 × 기간)를 알아야 결정 가능.
- 멀티 테넌시(여러 회사/사업부가 같은 DB를 공유하는지) 여부 미확정 — 확정되면 전체 테이블에 `tenant_id` 컬럼 추가 필요.
