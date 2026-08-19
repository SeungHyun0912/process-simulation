# 백엔드 개발 기획 개요

> 이 문서는 `docs/planning/` 하위 기획 문서들의 진입점이다. 각 문서는 요구사항 1~6에 1:1 대응한다.

## 1. 배경

`docs/schema/`에는 이미 다음과 같은 스키마 초안이 존재한다.

| 파일 | 내용 |
|---|---|
| `process-schema.json` | `COMMON_FIELD_DICTIONARY`(공통 필드 사전), `FIELD_META_REGISTRY`(필드→경로 매핑 레지스트리), `PROCESS_DEFINITION_INTENT`(공정 정의 입력 템플릿) |
| `process-simpy-map.json` | `PROCESS_BINDING_META`(그래프/자원/시간/전이/큐 바인딩 규칙), `SIMPY_RUNTIME_META`(시뮬레이션 실행 파라미터), `SIMPY_COMPILATION_INTENT`(컴파일 요청 계약) |
| `simpy-schema-compiler.json` | `COMPILER_MAPPING_RULE`(위 스키마들을 `compiled_graph_object`로 변환하는 규칙) |
| `isa88-schema.json` | ISA-88 기반 마스터 레시피 예시 (참고용, 배치 공정 스타일) |
| `docs/example/compiled_graph_object_example` | 컴파일러 최종 출력 예시 |

즉 "Meta Schema → 공정 정의 → 컴파일 → SimPy 실행"이라는 파이프라인의 **스펙(문서)** 은 이미 존재하지만, 이를 실제로 저장/관리/API로 노출/외부 업로드로 채우는 **백엔드 구현체**는 아직 없다.

## 2. 요구사항과 문서 매핑

| # | 요구사항 (사용자 원문 요약) | 상세 기획 문서 |
|---|---|---|
| 1 | SimPy 엔진 Input Data 표준화 — 자재 위치, 이동 경로/소요 시간, 공정별 원자재/반제품, 공정 시간 등을 통합하는 Meta Schema 구조 | [`01-meta-schema-design.md`](./01-meta-schema-design.md) |
| 2 | Meta Schema 기반으로 특정 공정의 프로세스를 관리 | [`02-process-management.md`](./02-process-management.md) |
| 3 | Meta Schema 기반, 외부에서 LLM으로 Excel/JSON/배열 형식 업로드 | [`03-llm-ingestion.md`](./03-llm-ingestion.md) |
| 4 | 공정 정보 / Meta Schema / 프로세스 관리를 RDB에 저장 | [`04-rdb-design.md`](./04-rdb-design.md) |
| 5 | 사용자 기반으로 공정 정보/프로세스를 수정하는 API | [`05-api-design.md`](./05-api-design.md) (CRUD 섹션) |
| 6 | 시뮬레이션 결과를 화면으로 전달하는 API | [`05-api-design.md`](./05-api-design.md) (Simulation 섹션) |
| 7 | (파생) 실제 공정 정보(DB/Excel)를 표준 스키마로 변환해 컴파일/시뮬레이션까지 End-to-End로 역검증 | [`06-e2e-reverse-validation.md`](./06-e2e-reverse-validation.md) |

## 3. 전체 아키텍처 (레이어)

```
 [외부 입력]                [백엔드]                                  [클라이언트]
 Excel/CSV ─┐
 JSON      ─┼─▶ (3) LLM Ingestion  ─▶ (1) Meta Schema 정규화 ─▶ (4) RDB 저장
 배열/텍스트─┘         │                                              │
                       ▼                                              │
                (2) Process 관리(CRUD, 버전, 상태)  ◀────── (5) 사용자 편집 API
                       │
                       ▼
              Compiler (COMPILER_MAPPING_RULE 구현)
                       │
                       ▼
              compiled_graph_object (RDB 저장, 버전 관리)
                       │
                       ▼
              SimPy Runtime Engine (실행)
                       │
                       ▼
              시뮬레이션 결과 (event_log/resource_log/wip_snapshot)
                       │
                       ▼
              (6) 결과 조회 API ──────────────────────────▶ 화면(대시보드)
```

레이어 책임 분리 원칙:

- **Meta Schema 레이어**: "필드가 무엇이고 어디에 위치하는가"만 정의. 값은 갖지 않는다. (`COMMON_FIELD_DICTIONARY` + `FIELD_META_REGISTRY` 확장)
- **Process 관리 레이어**: Meta Schema를 따르는 실제 데이터(제품, 라우팅, 설비, 위치, 레시피)의 CRUD/버전/상태.
- **Ingestion 레이어**: 비정형 입력을 Meta Schema에 맞는 초안(provisional)으로 변환. 사람 승인 전까지 `official`로 승격되지 않음.
- **Compiler 레이어**: 기존 `COMPILER_MAPPING_RULE` 스펙을 그대로 구현체로 옮김. 검증 게이트를 통과해야 산출물 생성.
- **Runtime 레이어**: `compiled_graph_object` + `SIMPY_RUNTIME_META`를 받아 실제 SimPy `env.run()`을 수행.
- **API 레이어**: 위 레이어들을 REST(+필요시 SSE/WebSocket)로 노출.

## 4. 단계별 로드맵 (제안)

| Phase | 범위 | 산출물 | 상태 |
|---|---|---|---|
| P0 | Meta Schema 확장 설계 + RDB 스키마 설계 확정 | `01`, `04` 문서 확정, ERD | 완료 |
| P1 | Process 관리 CRUD API (수동 입력 기준) | `02`, `05` 중 CRUD 부분 구현 | 완료 |
| P2 | Compiler 구현체 (`COMPILER_MAPPING_RULE` → 코드) | `ProcessRouting` → `compiled_graph_object` 변환기, `RuntimeProfile`/`CompileRun` | 완료 |
| P3 | SimPy Runtime 실행기 + 결과 저장/조회 API | `05` 중 시뮬레이션 실행/결과 API | 완료 |
| P4 | LLM 기반 업로드 파이프라인 | `03` 문서 구현 (Excel/JSON 업로드 → 초안 생성 → 검수 UI 연동) | 완료 (코드는 실제 Anthropic SDK로 구현, 라이브 호출은 이 환경에 API 키가 없어 미검증 — 아래 참고) |
| P5 | 실데이터(DB/Excel) 기반 E2E 역검증 | `06` 문서 구현 (P2·P3 완료 후 착수 — 표준 스키마 변환 → 컴파일 → SimPy 실행까지 실데이터로 관통 검증) | 계획 수립됨, 구현 예정 |

**P2 구현 메모**: 라우팅 레벨 검증(`/validate`, `/publish` — 끊긴 참조, 미해결 설비마스터)과 컴파일 전용 검증(`BLOCK_UNRESOLVED_PROCESSING_TIME` — std_speed 미해결)을 분리했다. 라우팅은 일부 스텝의 시간 정보가 아직 없어도 `published` 상태가 될 수 있지만, 컴파일은 그 상태에서 막힌다 (`compile_run.status = "blocked"`로 기록되고 `compiled_graph_object`는 `null`). 컴파일 실패는 `/publish`처럼 예외를 던지지 않고 `CompileRun` 행으로 남겨 감사 가능하게 했다.

**P3 구현 메모**: `app/services/simulation.py`가 `compiled_graph_object`를 실제 SimPy 이산 이벤트 시뮬레이션으로 실행한다. 핵심 v1 단순화 사항(향후 실사용 검증 후 확장 대상):
- 연속(continuous) 스텝은 단위별이 아니라 **최대 500개 단위 묶음(chunk)** 단위로 자원을 점유·처리한다 — 그렇지 않으면 30일 기본 시뮬레이션에서 스텝당 이벤트가 수백만 건이 되어 비현실적이다.
- **병렬 분기(parallel_split)는 산출량을 분기 수만큼 균등 분배**, **병합(merge)은 각 선행 분기에서 1개씩(또는 batch 스텝이면 1배치씩) 정확히 1:1로 소비** — 스키마에 분배 비율 필드가 없어 균등 분배를 v1 기본값으로 채택했다.
- transition의 `condition` 문자열은 저장만 하고 실행에는 반영하지 않는다(스펙상 "application_defined_expression"으로 미정의).
- 평균 리드타임은 개별 유닛을 추적하지 않고 **리틀의 법칙**(avg_wip / throughput_rate)으로 근사한다.
- SimulationRun은 **동기 실행**이다(대기열/워커 없음) — 5-스텝 케이블 라인 30일 시뮬레이션이 실제로 약 1.2초 걸림을 확인했고, 이 정도 규모에서는 비동기 인프라가 아직 필요 없다고 판단했다.
- 원자재 입고(`MaterialInboundPlan`)는 컴파일 시점이 아니라 **시뮬레이션 실행 시점**에 조회한다 — `material_inbound_overrides`로 실행별 오버라이드가 가능해야 한다는 요구사항([`01-meta-schema-design.md`](./01-meta-schema-design.md) 참고) 때문에, 그래프 위상(컴파일 결과)과 입고량(실행 시점 가변값)의 책임을 분리했다.

**P4 구현 메모**: `app/services/ingestion.py` + `app/services/llm_client.py`가 Anthropic API(`claude-opus-5`, `output_config.format=json_schema` 구조화 출력)로 원시 테이블을 캐노니컬 필드로 매핑한다.
- **엔드투엔드로 지원하는 대상은 5개 마스터 엔티티**(product/equipment_group/location/transport_route/recipe)뿐이다. `process_step`(라우팅 스텝)은 제외했다 — 승격하려면 대상 `ProcessRouting` 버전이 필요한데, 범용 업로드에는 그 컨텍스트가 없기 때문. 필요해지면 확장.
- 목표 스키마는 `entity_scope` 태그가 아니라 **`path_patterns`의 접두사**로 생성한다 (예: `"products[]."`) — `FIELD_META_REGISTRY`에서 같은 필드가 다른 entity_scope 태그를 달고 여러 엔티티에 걸쳐 재사용되는 경우가 실제로 있어서(`FM_PRODUCT_PRODUCT_ID`는 `entity_scope: product_context`이지만 `path_patterns`에 `"recipes[].product_id"`도 포함), entity_scope로만 걸러내면 레시피 업로드에서 product_id를 놓친다. 단, 접두사 뒤에 `.`이 더 있는 중첩 경로(`products[].cable_design.conductor.material` 등)는 제외한다 — canonical_key("material")가 conductor/insulation/sheath에서 중복되고, 우리 모델들은 어차피 이런 중첩 값을 평평한 컬럼으로 노출하지 않기 때문.
- 01번 문서에서 설계만 하고 실제로는 시딩하지 않았던 위치/이동경로 필드를 `docs/schema/process-schema-extensions.json`(신규)로 정식 등록했다 — 원본 `process-schema.json`은 건드리지 않고 레이어를 얹는 방식. `scripts/seed_meta_schema.py`가 이제 두 파일을 다 읽는다.
- **이 환경에는 `ANTHROPIC_API_KEY`도 `ant` CLI도 없어 실제 LLM 호출은 라이브로 검증하지 못했다.** 코드는 Anthropic Python SDK를 정확한 스펙대로 사용했고(`claude-api` 스킬 기준), 테스트는 `extract_structured`를 모킹해서 파이프라인 로직(엔티티 판별 → 스키마 생성 → 승격)만 검증했다. 실제 호출 확인은 API 키를 받으면 그때 진행.
- 업로드는 파일(`POST /ingestion/jobs/file`, csv/xlsx)과 JSON/배열 페이로드(`POST /ingestion/jobs/payload`)를 별도 엔드포인트로 분리했다 — 하나의 엔드포인트에서 멀티파트와 JSON 바디를 동시에 깔끔하게 받기 어려워서.

P4를 P0~P3 이후에 두는 이유: LLM 매핑의 목표 스키마(Meta Schema)와 저장 방식(RDB)이 먼저 안정화되어야 LLM 추출 결과의 정확도를 판단할 기준이 생기기 때문. 단, 문서화 자체는 지금 단계에서 함께 진행한다.

**P0~P4 완료 후 스키마 표현력 검토**: [`07-schema-gap-review.md`](./07-schema-gap-review.md)에서 "복잡한 공정(예: 하나의 투입 자재가 정해진 비율로 여러 산출물로 나뉘는 co-product 분기)을 지금 스키마로 표현할 수 있는가"를 감사했다. 당초 결론은 불가 — `ProcessStep`/`ProcessStepTransition`이 "1스텝 = 입력 1개 = 출력 1개"를 전제로 설계돼 있어, 분기 비율 필드 자체가 없었다. 그 외에도 Recipe의 수율/로스 필드가 컴파일러·시뮬레이터에 연결되지 않은 점, 여러 제품이 같은 설비를 공유할 때 자원 경합이 시뮬레이션 간에 반영되지 않는 점 등을 함께 정리해두었다.

**Phase A (co-product 비율 분기 + 비대칭 BOM 합류) 구현 완료**: `ProcessStepOutput` 테이블로 스텝의 산출물을 1:N으로 분리(`output_item_id`/`output_ratio`), `ProcessStepTransition`에 `output_item_id`(어떤 산출물을 나르는 전이인지)/`consumption_ratio`(merge 스텝의 비대칭 소비 비율)를 추가했다. 검증 게이트 3종(`BLOCK_STEP_HAS_NO_OUTPUT`/`BLOCK_TRANSITION_OUTPUT_ITEM_UNKNOWN`/`WARN_OUTPUT_RATIO_SUM`) 추가. `ProcessStep.output_item_id`는 하위호환 shim 없이 제거 — 이 프로젝트가 아직 프로덕션 데이터 없는 개발 단계라 깔끔한 컷을 택했다. "A설비에 1번 자재 투입 시 1-1/1-2가 6:4로 나온다" 예시를 API 전체 스택(DB→컴파일러→시뮬레이터)으로 재현해 정확히 60/40 분배되는 것을 확인했다.

**Phase B (`RoutingProductLink`, 멀티 제품 공유 네트워크) 구현 완료**: 여러 제품이 라우팅(=네트워크) 하나를 공유하고 각자 다른 entry/terminal 서브그래프를 소비할 수 있게 됐다. 컴파일러/시뮬레이터의 기존 실행 루프는 거의 그대로 두고(자원 풀이 이미 `compiled_graph_object` 전체 기준으로 한 번만 생성되므로 공유가 자동으로 반영됨), `compiled_graph_object.product_context`(단일)를 `product_contexts`(리스트)로 바꾸고, 시뮬레이션 결과에 `exit_qty_by_step`을 추가해 `GET .../results/summary?product_id=`로 제품별 처리량을 재구성할 수 있게 했다(`resource_utilization`은 공유 자원이라 필터링 없이 그대로). "원자재 → 공용 1번 공정 → 서로 다른 완제품 X/Y로 분기, 하류에서 설비를 공유" 시나리오를 실제 API로 재현해 공유 설비 가동률이 약 99.97%까지 올라가는 것과, 제품별 처리량이 올바르게 갈리는 것을 확인했다. 알려진 제약 하나(primary 제품의 `scope=product` 조회가 포크된 분기까지 포함하는 문제)는 `07-schema-gap-review.md` 6-7절에 기록해뒀다.

**Phase C (Recipe 수율/로스 연결, 07번 문서 3-3) 구현 완료**: `Recipe.length_factor`(`input_per_output`/`loss_rate`)가 정의만 되고 컴파일러·시뮬레이터 어디에도 읽히지 않던 "죽은 데이터" 문제를 해결했다. 새 FK 없이 `compiler.py::_select_recipe`가 `simpy-schema-compiler.json`의 `recipe_selection_rules`(정확 매치 → 그룹 매치 → 제품-무관 폴백)로 스텝마다 레시피를 매칭하고, `processing_time_plan`에 `recipe_id`/`input_qty_per`/`input_qty_per_source`/`loss_rate`를 노출한다(스텝 자신의 `input_qty_per`가 있으면 그 값이 레시피보다 우선). `simulation.py::step_process`는 이 값으로 (1) 입력 컨테이너 소비량을 `input_qty_per`만큼 스케일링, (2) 산출량에 `qty * (1 - loss_rate)`를 적용해 하류로 넘기되 자원 점유 시간은 로스 반영 전 수량 기준으로 유지한다. `input_per_output=2.0`(원료 2단위당 완제품 1단위)·`loss_rate=0.1`(10% 로스)인 레시피로 원료 100단위 투입 시 정확히 45단위가 산출되는 것을 API 전체 스택(DB→컴파일러→시뮬레이터)으로 재현해 확인했다.

## 5. 미해결 전제 (다음 대화에서 확인 필요)

- RDB 종류 미확정 (PostgreSQL 가정하고 진행, JSONB 활용 전제) — [`04-rdb-design.md`](./04-rdb-design.md) 참고.
- 인증/사용자 모델(SSO 연동 여부, 역할 체계)이 미확정 — [`05-api-design.md`](./05-api-design.md)에서 최소 가정으로 진행.
- LLM 제공자/모델 미확정 — [`03-llm-ingestion.md`](./03-llm-ingestion.md)에서는 모델 중립적으로 "구조화 추출(Structured Extraction)" 인터페이스만 정의.
