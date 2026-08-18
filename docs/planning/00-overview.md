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

| Phase | 범위 | 산출물 |
|---|---|---|
| P0 | Meta Schema 확장 설계 + RDB 스키마 설계 확정 | `01`, `04` 문서 확정, ERD |
| P1 | Process 관리 CRUD API (수동 입력 기준) | `02`, `05` 중 CRUD 부분 구현 |
| P2 | Compiler 구현체 (`COMPILER_MAPPING_RULE` → 코드) | `PROCESS_DEFINITION_INTENT` → `compiled_graph_object` 변환기 |
| P3 | SimPy Runtime 실행기 + 결과 저장/조회 API | `05` 중 시뮬레이션 실행/결과 API |
| P4 | LLM 기반 업로드 파이프라인 | `03` 문서 구현 (Excel/JSON 업로드 → 초안 생성 → 검수 UI 연동) |
| P5 | 실데이터(DB/Excel) 기반 E2E 역검증 | `06` 문서 구현 (P2·P3 완료 후 착수 — 표준 스키마 변환 → 컴파일 → SimPy 실행까지 실데이터로 관통 검증) |

P4를 마지막에 두는 이유: LLM 매핑의 목표 스키마(Meta Schema)와 저장 방식(RDB)이 먼저 안정화되어야 LLM 추출 결과의 정확도를 판단할 기준이 생기기 때문. 단, 문서화 자체는 지금 단계에서 함께 진행한다.

## 5. 미해결 전제 (다음 대화에서 확인 필요)

- RDB 종류 미확정 (PostgreSQL 가정하고 진행, JSONB 활용 전제) — [`04-rdb-design.md`](./04-rdb-design.md) 참고.
- 인증/사용자 모델(SSO 연동 여부, 역할 체계)이 미확정 — [`05-api-design.md`](./05-api-design.md)에서 최소 가정으로 진행.
- LLM 제공자/모델 미확정 — [`03-llm-ingestion.md`](./03-llm-ingestion.md)에서는 모델 중립적으로 "구조화 추출(Structured Extraction)" 인터페이스만 정의.
