# 06. 실데이터 기반 End-to-End 역검증 (Reverse Validation)

대응 요구사항: **(신규/파생)** — Meta Schema → Process 관리 → Compiler → SimPy Runtime 전체 파이프라인이 실제 공정 정보(DB/Excel)로도 끝까지 동작하는지 실증적으로 검증

> 이 문서는 [`00-overview.md`](./00-overview.md)의 로드맵에 **P5**로 편입된다. P2(컴파일러)·P3(SimPy 런타임)가 먼저 구현되어 있어야 의미가 있다.

## 1. 목적 및 배경

P0~P4는 전부 "전방(forward)" 방향이다 — 스키마를 설계하고(01), 사용자가 그 스키마에 맞춰 데이터를 채우거나(02) LLM이 비정형 입력을 스키마에 맞춰 변환한다(03).

이 문서는 반대 방향을 다룬다: **이미 현업에서 신뢰하고 쓰고 있는 공정 정보**(사내 DB의 공정 마스터 테이블, 현업이 관리하는 Excel)를 표준 Meta Schema로 변환한 뒤, 그 결과를 실제로 **컴파일하고 SimPy로 실행까지** 시켜본다. "필드가 잘 매핑되었는가"가 목적이 아니라, **"이 스키마·컴파일러·런타임 설계가 실제 공정의 복잡도를 끝까지 감당하는가"**를 실데이터로 증명하는 것이 목적이다.

사용자 확인 결과, 이 기능의 검증 범위는 **컴파일/시뮬레이션 End-to-End 검증**으로 한정한다 (아래 2장 참고).

## 2. 범위

**포함:**
- DB/Excel 공정 정보 → 표준 스키마 변환 → ProcessRouting(draft) 등록 → 검증 게이트 → 컴파일 → SimPy 실행까지 **끝까지 도는지** 확인.
- 실패 시 **어느 단계에서, 왜** 끊겼는지 구조화된 진단 리포트 제공.

**범위 밖 (명시적 제외):**
- 무손실 라운드트립 비교(원본 ↔ 표준 스키마 ↔ 역변환 결과 diff). 필요해지면 별도 문서로 분리.
- 참조무결성/그래프완결성 판정 규칙 자체의 재설계 — [`02-process-management.md`](./02-process-management.md)의 `validated` 게이트를 그대로 재사용할 뿐, 새 규칙을 만들지 않는다.
- 시뮬레이션 결과와 실측 KPI(실제 처리량/리드타임 등) 비교. "정확한 결과인가"가 아니라 "끝까지 도는가"만 다룬다 — 이건 향후 별도 과제.

## 3. 핵심 설계 원칙 — 신규 로직이 아니라 오케스트레이션

이 기능은 **새 도메인 로직을 추가하지 않는다.** 이미 설계된 4개 레이어의 API를 실데이터로 순서대로 호출해서, 레이어 간 계약(contract)이 실제로 맞물리는지 검증하는 **오케스트레이터**다.

```
03 Ingestion API → 02 Process 관리 API(validate) → 05 Compile API → 05 Simulation API
```

따라서 이 문서에서 새로 정의하는 것은 "① 소스 어댑터(DB/Excel → 03 파이프라인 입력)"와 "② 4단계를 엮어서 추적하는 오케스트레이션 로그"뿐이다.

## 4. 소스 어댑터

### 4-1. DB 소스

- 대상: 레거시 MES/ERP/자체 관리 DB의 공정 마스터 테이블(제품/라우팅/설비/위치 등).
- DB는 이미 구조화되어 있어 컬럼이 고정적인 경우가 많다 → **선언적 매핑 프로파일**(테이블/컬럼 → `canonical_key` 매핑, 1회 작성 후 재사용)로 결정적 변환을 1차 경로로 사용한다. LLM 추론이 필요 없는 경우가 대부분이라는 점이 Excel과 다르다.
- 매핑 프로파일이 없는 신규 테이블/모호한 컬럼은 표를 정규화(rows+headers)해서 [`03-llm-ingestion.md`](./03-llm-ingestion.md)의 3단계(LLM 구조화 추출)에 그대로 태운다 — 즉 DB 커넥터는 "03 파이프라인의 또 다른 입력 소스"로 어댑팅되는 것이지 별도 매핑 로직을 새로 만드는 게 아니다.
- 운영 원칙: **read-only 계정만 사용**, 시점 고정 스냅샷 방식으로 조회 (운영 DB에 쓰기/부하 영향 금지, 필요시 야간 배치).

### 4-2. Excel 소스

- [`03-llm-ingestion.md`](./03-llm-ingestion.md) 파이프라인을 그대로 재사용한다 (신규 개발 없음). 차이는 "사람이 검수 후 승인"에서 끝나는 것이 아니라, 승인 즉시(또는 검수를 건너뛰고 provisional 상태로) 5장의 E2E 파이프라인이 이어서 자동 실행된다는 점뿐이다.

## 5. E2E 검증 파이프라인

```
[소스: DB 테이블 스냅샷 | Excel 파일]
        │
        ▼
1) Source Adapter        표 정규화(rows+headers) 또는 매핑 프로파일 직접 적용
        │
        ▼
2) 표준 스키마 변환        매핑 프로파일 우선 적용, 미매핑 컬럼은 03문서 LLM 매핑으로 폴백
        │                 산출물: PROCESS_DEFINITION_INTENT 형태 draft (schema_status=provisional)
        ▼
3) Process 등록           ProcessRouting(status=draft) + 마스터데이터(Product/Equipment/Location 등) upsert
        │
        ▼
4) 검증 게이트             02문서 validate 재사용 — graph_validation_rules / compile_blocking_rules
        │                 ✗ 실패 → STOP, failed_stage=validation
        ▼
5) 컴파일                 05문서 POST /compile-runs 재사용 → compiled_graph_object 생성
        │                 ✗ 실패 → STOP, failed_stage=compile
        ▼
6) 시뮬레이션 실행(smoke run)  05문서 POST /simulation-runs 재사용, 최소 1 replication·짧은 horizon
        │                 ✗ 실패 → STOP, failed_stage=simulate
        ▼
7) E2E 검증 리포트         단계별 성공/실패 + 실패 원인 + (성공 시) 요약 결과 링크
```

## 6. 실패 진단 — 이 기능의 핵심 가치

전부 통과하면 좋지만, 이 기능의 진짜 가치는 **"어디서, 왜 끊기는지"를 구조화해서 알려주는 것**이다. 실데이터는 스키마 설계 당시 예상하지 못한 조합(빠진 참조, 순환 라우팅, 극단적 파라미터 등)을 자연스럽게 드러낸다.

| Stage | 실패 유형 예시 | 리포트에 남기는 정보 (기존 계약 재사용) |
|---|---|---|
| mapping | 매핑 안 된 컬럼, confidence 미달 필드 | `unmapped_columns[]`, `missing_fields[]` (03문서 `PROCESS_DEFINITION_INTENT` 재사용) |
| validation | 참조 미해결(`ref_missing`), 그래프 `incomplete` | `unresolved_reference_paths[]`, `graph_completeness_status` (01/02문서 재사용) |
| compile | `compile_blocking_rules` 위반 (예: `BLOCK_MISSING_RESOURCE_MASTER`) | 위반 규칙 ID, 위반 대상 `step_no`/필드 |
| simulate | SimPy 예외, deadlock(무한 대기), 비정상 종료 | 예외 스택, 정지된 `sim_time`, 마지막 이벤트 |

이 실패 로그가 누적되면 [`01-meta-schema-design.md`](./01-meta-schema-design.md) §9 "미해결 질문"에 대한 **실증 근거**가 된다. 예: "위치 계층 구조가 필요한가?"라는 질문이 실데이터에서 반복적으로 mapping 실패를 유발하면, 그 항목의 우선순위를 실데이터 빈도로 정당화할 수 있다.

## 7. RDB 확장 ([`04-rdb-design.md`](./04-rdb-design.md) 확장)

```
source_connection
  id (PK), source_type (db/excel), name,
  connection_config (JSONB — 비밀번호 등 민감정보는 저장 금지, secret manager 참조 키만 저장),
  is_readonly (db 소스는 true 강제), created_by, created_at

source_mapping_profile
  id (PK), source_connection_id (FK, nullable — excel은 파일 단위라 nullable),
  entity_scope, column_mapping (JSONB: {raw_column: common_field_id}),
  version, created_by, created_at

e2e_validation_run
  id (PK),
  source_connection_id (FK -> source_connection, nullable),
  upload_job_id (FK -> upload_job, nullable),               -- Excel 경로일 때
  status (running/succeeded/failed),
  failed_stage (mapping/validation/compile/simulate, nullable),
  resulting_routing_id (FK -> process_routing, nullable),
  resulting_compile_run_id (FK -> compile_run, nullable),
  resulting_simulation_run_id (FK -> simulation_run, nullable),
  failure_detail (JSONB),
  started_at, finished_at, requested_by
```

`e2e_validation_run`은 새 파이프라인 상태를 만드는 테이블이 아니라, **이미 존재하는 4개 FK(upload_job / process_routing / compile_run / simulation_run)를 하나의 실행으로 엮어 추적하는 오케스트레이션 로그**다.

## 8. API ([`05-api-design.md`](./05-api-design.md) 확장)

```
POST   /e2e-validation-runs
  body: { source_type: "db"|"excel", source_connection_id? | file, mapping_profile_id? }
  → 202 Accepted, 오케스트레이터가 5장의 1)~7) 단계를 순차 실행(비동기)

GET    /e2e-validation-runs/{id}
  → { status, failed_stage?, stage_results: {mapping, validation, compile, simulate},
      links: { routing_id, compile_run_id, simulation_run_id } }

GET    /e2e-validation-runs/{id}/report
  → 6장 표 형태의 상세 실패 진단 리포트

GET/POST  /source-connections            DB 커넥션 등록/관리 (read-only 검증 포함)
GET/POST  /source-mapping-profiles       매핑 프로파일 관리 (재사용 자산)
```

## 9. 운영/보안 고려사항

- DB 소스는 반드시 **read-only 계정** + 시점 고정 스냅샷. 운영 시스템에 쓰기/과도한 조회 부하를 주지 않는다.
- `connection_config`에 자격증명 평문 저장 금지 — secret manager(또는 최소 환경변수) 참조 키만 RDB에 저장.
- E2E 실행은 컴파일+시뮬레이션까지 포함하는 무거운 작업 → [`05-api-design.md`](./05-api-design.md)의 비동기 워커/큐에 편승하고, 동시 실행 수를 제한한다.

## 10. 로드맵 반영

| Phase | 범위 | 선행 조건 |
|---|---|---|
| P5 | 본 기능(E2E 역검증 오케스트레이터 + DB/Excel 소스 어댑터) | **P2(컴파일러) + P3(SimPy 런타임) 완료 필수.** DB 매핑 프로파일 방식 자체는 LLM 불필요하므로 P4(LLM 업로드)와 독립적으로 먼저 착수 가능 — 단, Excel 경로는 P4 완료 후 재사용. |

## 11. 미해결 질문

- 대상 레거시 DB의 실제 종류/스키마가 아직 미확정 — 커넥터 구현 전 확인 필요.
- "smoke run"의 기준(replication 수, horizon 길이)을 어떻게 정할지 — 너무 짧으면 deadlock 같은 장기 이슈를 못 잡고, 너무 길면 검증 자체가 무거워진다.
- 매핑 프로파일이 없는 신규 DB 테이블이 나타났을 때 LLM 폴백을 자동으로 태울지, 사람이 먼저 프로파일을 작성하도록 강제할지.
- E2E 실행이 실패했을 때 부산물로 남는 `draft` ProcessRouting/마스터 데이터를 그대로 둘지(다음 재시도에 재사용), 실행 단위로 정리(rollback)할지.
