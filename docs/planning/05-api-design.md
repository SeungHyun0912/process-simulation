# 05. API 설계

대응 요구사항: **(5) 사용자 기반으로 수정 가능한 API**, **(6) 시뮬레이션 결과를 화면으로 전달하는 API**

## 1. 원칙

- REST + JSON. 리소스는 [`04-rdb-design.md`](./04-rdb-design.md) 테이블과 1:1에 가깝게 대응.
- `FIELD_META_REGISTRY.editable = false`인 필드(파생값, 예: `std_time_per`)는 **쓰기 요청 바디에 포함되어도 서버가 무시하고 재계산** — 클라이언트가 잘못된 파생값을 강제로 넣는 것을 원천 차단.
- 모든 변경은 [`02-process-management.md`](./02-process-management.md)의 상태 모델(`draft/validated/published/...`)을 존중 — `published` 리소스는 직접 수정 대신 새 버전 생성을 유도.
- 인증/인가는 최소 가정: `app_user.role`(viewer/editor/approver/admin) 기반 RBAC. 실제 인증 방식(SSO/OAuth 등)은 별도 확인 필요.

## 2. Meta Schema API (읽기 중심)

```
GET  /meta-schema/common-fields                 전체 공통 필드 목록
GET  /meta-schema/field-mappings?entity_scope=  경로 매핑 목록 (프런트 동적 폼 생성용)
```

## 3. 마스터 데이터 API (요구사항 5)

제품/설비/위치/경로/레시피 각각 동일한 CRUD 패턴:

```
GET    /products                     목록 (필터: status, product_type)
POST   /products                     생성
GET    /products/{product_id}
PATCH  /products/{product_id}        부분 수정 (editable 필드만 반영)
DELETE /products/{product_id}        소프트 삭제(status=inactive) 권장, 하드 삭제 지양

GET/POST/PATCH/DELETE  /equipment-groups, /equipments
GET/POST/PATCH/DELETE  /locations, /transport-routes      (01 확장분)
GET/POST/PATCH/DELETE  /recipes
```

모든 쓰기 응답은 `validation_warnings[]`(차단은 아니지만 참조 미해결 등)를 포함해 즉시 피드백.

## 4. Process(라우팅) 관리 API (요구사항 2, 5)

```
GET    /products/{product_id}/routings                 버전 목록
POST   /products/{product_id}/routings                 신규 라우팅(버전) 생성, 기본 status=draft
GET    /products/{product_id}/routings/{version}        전체 그래프 조회 (steps + transitions + logistics)
PATCH  /products/{product_id}/routings/{version}        메타 정보 수정 (draft 상태에서만 허용)
POST   /products/{product_id}/routings/{version}/steps                스텝 추가
PATCH  /products/{product_id}/routings/{version}/steps/{step_no}      스텝 수정
DELETE /products/{product_id}/routings/{version}/steps/{step_no}      스텝 삭제
POST   /products/{product_id}/routings/{version}/clone                새 버전으로 복제

POST   /products/{product_id}/routings/{version}/validate   검증 실행 → validation_report 반환 (저장은 안 함)
POST   /products/{product_id}/routings/{version}/publish    draft/validated → published 전이 (approver 권한)
GET    /products/{product_id}/routings/{version}/diff?against={other_version}   버전 간 diff
```

- `validate`는 [`00-overview.md`](./00-overview.md)에서 언급한 컴파일러의 `graph_validation_rules`/`compile_blocking_rules`를 실제 컴파일 없이 미리 실행하는 "dry-run" 성격.
- 상태가 `published` 이상인 라우팅에 `PATCH`/`POST steps`/`DELETE steps` 요청이 오면 `409 Conflict` + "새 버전을 생성하라"는 안내 반환.

## 5. Ingestion API (요구사항 3, [`03-llm-ingestion.md`](./03-llm-ingestion.md) 5장 재정리)

```
POST   /ingestion/jobs                 파일 업로드 (multipart) 또는 JSON/배열 페이로드
GET    /ingestion/jobs/{id}
GET    /ingestion/jobs/{id}/draft
PATCH  /ingestion/jobs/{id}/mapping
POST   /ingestion/jobs/{id}/approve    → 성공 시 04번 문서의 마스터 테이블/ProcessRouting(draft)에 반영
```

## 6. 컴파일 API

```
POST   /compile-runs
  body: { product_id, routing_version, binding_meta_version?, runtime_profile_id? }
  →  COMPILER_MAPPING_RULE 구현체 실행, compiled_graph_object 저장 후 반환
GET    /compile-runs/{id}                 결과 + validation_report 조회
```

## 7. 시뮬레이션 실행/결과 API (요구사항 6 — 핵심)

```
POST   /simulation-runs
  body: { compile_run_id, runtime_profile_id, random_seed?, replication_count? }
  →  202 Accepted, status=queued (실행은 비동기 워커에서 SimPy env.run())

GET    /simulation-runs/{id}
  →  { status, progress(%), started_at, finished_at, error_message? }

GET    /simulation-runs/{id}/results/summary
  →  simulation_result_summary (throughput, avg_wip, avg_lead_time, resource_utilization, bottleneck_step_no)

GET    /simulation-runs/{id}/results/events?from=&to=&step_no=&limit=&cursor=
  →  simulation_event_log 페이지네이션 조회 (대용량 대비 커서 기반)

GET    /simulation-runs/{id}/results/wip-snapshot?interval=
  →  시간대별 WIP 스냅샷 (대시보드 시계열 차트용)

GET    /simulation-runs/{id}/results/resource-utilization
  →  스텝/설비별 가동률 (대시보드 바 차트용)
```

### 진행률/실시간 전달

시뮬레이션이 수초~수분 걸릴 수 있으므로:

- 기본: 클라이언트가 `GET /simulation-runs/{id}` 폴링.
- 개선안: `GET /simulation-runs/{id}/stream` (Server-Sent Events)로 진행률/부분 결과 push — 화면에 "진행 중" 표시가 필요하면 이 방식을 권장.

### 비교/시나리오

```
POST  /simulation-runs/compare
  body: { simulation_run_ids: [...] }
  →  여러 실행의 summary를 나란히 비교 (시나리오 A/B 비교 화면 지원)
```

## 8. 감사/권한

```
GET  /audit-logs?entity_type=&entity_id=       변경 이력 조회 (누가/언제/무엇을 바꿨는지)
```

- 모든 쓰기 API는 `app_user` 컨텍스트를 요구하고, 처리 후 `audit_log`에 diff 기록.
- `publish`, `approve` 같은 승인성 액션은 `approver`/`admin` 역할만 허용.

## 9. 응답 계약 재사용

신규 응답 스키마를 새로 설계하지 않고 기존 문서의 구조를 그대로 API 응답으로 사용한다:

| API | 응답 바디 구조 근거 |
|---|---|
| `POST /compile-runs` | `docs/example/compiled_graph_object_example` |
| `POST /*/validate` | `PROCESS_DEFINITION_INTENT.validation_report` |
| `GET /simulation-runs/{id}` | `SIMPY_RUNTIME_META.validation_status` + 실행 상태 필드 결합 |

## 10. 미해결 질문

- 인증 방식(사내 SSO, OAuth2, API Key 등) 미확정.
- 프런트엔드 프레임워크/실시간 전달 방식(SSE vs WebSocket vs 단순 폴링) 선호 여부 미확인 — 위 설계는 SSE를 "개선안"으로만 제시.
- 시뮬레이션 실행 큐/워커 구조(단순 백그라운드 태스크 vs Celery/RQ 같은 큐 시스템) 필요 여부는 동시 실행 요청 규모에 따라 결정 필요.
