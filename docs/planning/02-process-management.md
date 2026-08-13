# 02. Process 관리 — Meta Schema 기반 프로세스 운영

대응 요구사항: **(2) Meta Schema 구조를 기반으로 특정 공정의 프로세스로 관리**

## 1. 핵심 개념

Meta Schema(01)는 "필드가 어떤 모양인지"만 정의한다. 이 문서는 그 필드를 채운 **실제 데이터 인스턴스**를 어떻게 하나의 "프로세스"로 취급하고 생명주기를 관리할지 정의한다.

## 2. 엔티티 계층

```
Product (제품 마스터)
  └─ ProcessRouting (제품별 공정 그래프, 버전 존재)  ── "하나의 프로세스"
        └─ ProcessStep (라우팅 내 개별 스텝, step_no)
              ├─ StepTransition (next_steps, 조건부 전이)
              └─ StepLogistics (입/출 위치, 이동 경로 참조) — 01 문서 확장분

Equipment / EquipmentGroup (설비 마스터)
Location (위치 마스터)              — 01 문서 확장분
TransportRoute (이동 경로 마스터)   — 01 문서 확장분
Recipe (레시피, 설비/그룹 단위 처리 파라미터)
```

"프로세스(Process)"의 단위는 **ProcessRouting 1건 = 제품 1개의 특정 버전 공정 그래프**로 정의한다. 이는 기존 `PROCESS_DEFINITION_INTENT.process_graph` (product_id + steps[] + graph_completeness_status)와 정확히 대응된다.

## 3. 생명주기 (Status Model)

기존 스키마에 이미 있는 두 상태값을 재사용/연결한다.

- `schema_status`: `provisional` → `official` (필드/스텝 단위, 데이터 신뢰도)
- `graph_completeness_status`: `incomplete` → `provisional` → `complete` (그래프 전체 완결성), `blocked`(참조 오류로 진행 불가)

여기에 **ProcessRouting 단위 운영 상태**를 추가한다:

| 상태 | 의미 | 전이 조건 |
|---|---|---|
| `draft` | 작성/수정 중, 아직 검증 안 됨 | 생성 시 기본값 |
| `validated` | `COMPILER_MAPPING_RULE`의 validation_gates 통과 | 검증 API 호출 성공 |
| `published` | 사용자가 확정 승인, 컴파일/시뮬레이션 대상으로 지정 가능 | 승인 액션 (권한 필요) |
| `compiled` | 컴파일러가 `compiled_graph_object` 생성 완료 | 컴파일 API 성공 |
| `archived` | 더 이상 사용하지 않음(신버전으로 대체됨 등) | 새 버전 published 시 이전 버전 자동 archived (설정 가능) |

상태 전이는 단방향이 아니라 `published`에서 수정이 발생하면 새로운 **버전(version)** 이 생성되고 기존 published 버전은 유지된다(불변성 보장, 시뮬레이션 재현성을 위해 필수).

## 4. 버전 관리 원칙

- `ProcessRouting`은 `(product_id, version)` 복합키로 식별. `version`은 `draft-v1`, `draft-v2`, `v1.0` 등 문자열(기존 템플릿의 `"version":"draft-v1"` 관례 계승).
- 특정 시점에 제품당 **활성(active) 버전은 최대 1개**로 제한 — 시뮬레이션/컴파일 요청 시 버전을 명시하지 않으면 active 버전을 기본값으로 사용.
- 버전 승격/전환은 감사 로그(누가/언제/왜)를 남긴다 → [`04-rdb-design.md`](./04-rdb-design.md)의 `audit_log` 테이블과 연결.

## 5. 참조 무결성 관리

기존 `reference_status` (`resolved`/`master_missing`/`ref_missing`/`provisional`) 개념을 프로세스 관리 레이어의 핵심 기능으로 승격한다.

- 저장 시점(save)에는 참조 무결성 검사를 **경고만** 하고 저장을 막지 않는다 (편집 도중에는 미완성 상태 허용).
- `validated` 상태로 전이할 때는 `COMPILER_MAPPING_RULE.graph_validation_rules` / `compile_blocking_rules`를 그대로 적용해 **차단(block)** 한다.
- 참조 대상: `equipment_group` → `equipments[].group_id`, `input/output_item_id` → 품목 마스터, (신규) `input_location_id`/`output_location_id` → `locations[].location_id`, `inbound_route_id` → `transport_routes[].route_id`.

## 6. "관리"의 의미 — 구체적 기능 목록

1. **조회**: 제품별 라우팅 목록, 버전별 diff, 그래프 시각화용 nodes/edges 조회 (컴파일 전에도 draft 그래프를 볼 수 있어야 함).
2. **편집**: 스텝 추가/삭제/순서 변경, 필드 값 수정 — `FIELD_META_REGISTRY.editable` 플래그가 `false`인 필드(예: `std_time_per`, derived)는 서버가 직접 수정 거부하고 원본 필드(`std_speed`) 수정을 유도.
3. **검증**: on-demand로 `validation_report` 재계산 (그래프 완결성, dangling reference, 미해결 참조 목록).
4. **승격/승인**: `draft → validated → published` 상태 전이 액션.
5. **복제**: 기존 라우팅을 베이스로 새 버전 생성 (유사 제품 등록 시 유용).
6. **비교**: 두 버전 간 필드/그래프 구조 diff (시뮬레이션 결과 비교의 전제조건).

## 7. 다른 문서와의 연결

- 데이터 저장 스키마 → [`04-rdb-design.md`](./04-rdb-design.md)
- 위 CRUD/검증/승인 기능의 API 표면 → [`05-api-design.md`](./05-api-design.md)
- 이 레이어에 데이터를 채우는 또 다른 경로(LLM 업로드) → [`03-llm-ingestion.md`](./03-llm-ingestion.md) (LLM 업로드 결과도 결국 `draft` 상태의 ProcessRouting/마스터 데이터로 들어옴)

## 8. 미해결 질문

- "프로세스"를 제품 단위(ProcessRouting)로만 정의할지, 제품과 무관한 공통 공정 템플릿(예: "도금 공정 표준 절차")도 별도 관리 대상으로 둘지 — 1차 범위는 제품 단위로 한정, 공통 템플릿은 향후 `process_group_id` 기반 재사용으로 대체 가능한지 검토 필요.
- 버전 자동 archive 정책(신규 published 시 자동 archive vs 사용자가 명시적으로 archive) — 기본은 수동으로 제안.
