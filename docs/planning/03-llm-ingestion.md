# 03. LLM 기반 외부 업로드 (Ingestion)

대응 요구사항: **(3) Meta Schema 기반, 외부에서 LLM을 사용해서 Excel/JSON/배열 형식 등을 Upload**

## 1. 목표

사용자가 표준 형식을 몰라도, 갖고 있는 엑셀/JSON/CSV/배열 데이터를 업로드하면 LLM이 이를 읽고 [`01-meta-schema-design.md`](./01-meta-schema-design.md)의 Meta Schema(Common Field + Field Meta Registry)에 맞는 **초안(draft) 데이터**로 변환한다. 사람은 결과를 검수/보정만 하면 된다.

## 2. 왜 LLM인가 (매핑 문제의 본질)

전통적 ETL은 "컬럼명 = 필드명"을 가정하지만, 실제 엑셀은 `공정명`, `공정 이름`, `Process Nm`처럼 제각각이고, 시트 구조도 제조사/팀마다 다르다. LLM은:

- 컬럼 헤더 + 샘플 값(row 몇 개)을 보고 `FIELD_META_REGISTRY`의 `canonical_key` 중 어디에 대응하는지 추론
- enum_domain이 있는 필드(`product_type: [material, semi, finished]`)는 실제 값을 enum으로 정규화 (예: "완제품" → `finished`)
- 여러 시트/여러 파일에 흩어진 정보(제품 시트 + 공정 시트 + 설비 시트)를 엔티티별로 분리해 조립

## 3. 파이프라인

```
1) 업로드 접수         POST /ingestion/jobs  (파일: xlsx/csv/json, 또는 원시 배열/텍스트 페이로드)
2) 사전 처리(Parsing)   - xlsx → 시트별 표 추출 (pandas/openpyxl)
                        - csv → 표 1개
                        - json/array → 그대로 구조 파악
3) LLM 구조화 추출      - 목표 스키마 = FIELD_META_REGISTRY를 JSON Schema/함수 호출 스키마로 변환한 것
                        - 입력: 헤더 + 샘플 N행(전체 아님, 토큰 절약) + 시트명/파일명 메타
                        - 출력: PROCESS_DEFINITION_INTENT.template 형태의 부분 채움 + 매핑 근거
4) 매핑 감사 기록        raw_column → canonical_field, confidence, LLM 판단 근거 저장 (재사용/재현성)
5) 정규화 및 검증        cast_to_string(step_no), enum 정규화, 참조 무결성 1차 점검
6) 초안 저장            모든 결과는 schema_status=provisional, value_role은 원본이 명시값이면 raw,
                        LLM 추정이면 assumption 으로 태깅 (PROCESS_DEFINITION_INTENT.assumptions[] 활용)
7) 사람 검수            검수 API/화면에서 assumptions[]·missing_fields[]·unmapped 컬럼을 검토
8) 승격                 승인 시 provisional → official, ProcessRouting 상태 draft로 저장
```

## 4. 목표 스키마를 LLM 입력으로 변환

`FIELD_META_REGISTRY.entries`의 각 항목은 이미 `canonical_key`, `canonical_type`, `enum_domain`, `entity_scope`를 갖고 있어 **그대로 구조화 출력 스키마의 소스**로 쓸 수 있다. 즉 별도의 "LLM용 스키마"를 새로 설계하지 않고, `entity_scope`별로 그룹핑해 JSON Schema를 **자동 생성**한다.

```
entity_scope: "product_master"       → Product 추출용 스키마
entity_scope: "routing_step"         → ProcessStep 추출용 스키마
entity_scope: "equipment_master"     → Equipment 추출용 스키마
entity_scope: "location_master"      → Location 추출용 스키마 (01 확장분)
entity_scope: "transport_route_master" → TransportRoute 추출용 스키마 (01 확장분)
```

→ 스키마가 늘어나도(신규 `entity_scope`) 이 자동 생성 로직은 코드 변경 없이 동작해야 한다 (핵심 설계 목표: Meta Schema가 단일 진실 소스).

## 5. 입력 형식별 처리 차이

| 입력 형식 | 특이사항 |
|---|---|
| Excel(xlsx) | 시트 1개 = 엔티티 1개로 가정하되, LLM이 시트명/헤더로 실제 엔티티 재판별. 병합 셀/헤더 2행 등 비정형 레이아웃은 전처리 단계에서 표 형태로 정규화 후 LLM에 전달. |
| CSV | 단일 표, 인코딩(UTF-8/CP949) 자동 감지 필요 (한글 데이터 다수 예상). |
| JSON | 이미 구조화되어 있으므로 LLM은 "매핑"만 수행 (필드명 변환), 파싱 단계 불필요. 기존 필드명이 canonical_key와 다르면 매핑 테이블 생성. |
| 배열/텍스트(자유 형식) | 가장 불확실. LLM에게 "이 텍스트에서 표 구조를 먼저 추출하라"는 1단계 프롬프트 추가 (2-pass: 구조 추출 → 필드 매핑). |

## 6. 신뢰도와 사람 개입 지점

- 각 매핑에 `confidence`(0~1) 부여. 임계값(예: 0.6) 미달 필드는 자동 승인 대상에서 제외하고 `missing_fields[]`에 기록.
- 동일 canonical_key에 후보 컬럼이 2개 이상이면 자동 매핑하지 않고 사람에게 선택지 제시.
- 이미 존재하는 `promotion_candidates[]`, `assumptions[]`, `missing_fields[]` (PROCESS_DEFINITION_INTENT 스키마)를 그대로 이 파이프라인의 출력 계약으로 사용 — 신규 필드 설계 불필요.

## 7. 재사용/학습 루프

- 사람이 매핑을 수정하면 그 결과(파일 출처 조직/템플릿 + raw_column → canonical_field 확정 매핑)를 **매핑 사전(alias dictionary)** 에 저장.
- 다음 업로드 시 동일 컬럼명이 나오면 LLM 호출 전에 사전 매칭을 먼저 시도 (비용 절감 + 정확도 향상). 이 사전은 RDB 테이블(`upload_field_alias`)로 관리 → [`04-rdb-design.md`](./04-rdb-design.md).

## 8. API 표면 (요약, 상세는 05번 문서)

```
POST   /ingestion/jobs                 파일/페이로드 업로드, 비동기 작업 생성
GET    /ingestion/jobs/{id}            상태 조회 (parsing/extracting/awaiting_review/completed/failed)
GET    /ingestion/jobs/{id}/draft      LLM 추출 결과(초안) 조회 — PROCESS_DEFINITION_INTENT 형태
PATCH  /ingestion/jobs/{id}/mapping    특정 컬럼의 매핑을 사람이 수정
POST   /ingestion/jobs/{id}/approve    검수 완료 → ProcessRouting/마스터 데이터로 승격(promote)
```

## 9. 실패/예외 처리

- LLM 추출 실패(형식 인식 불가) → `failed` 상태 + 원인 메시지, 원본 파일은 보존.
- 부분 성공(일부 시트만 인식) → `awaiting_review` 상태로 두고 인식 안 된 시트는 `unmapped_sheets[]`에 노출.
- 대용량 파일(수만 행) → 표 전체를 LLM에 넣지 않고 헤더+샘플로 매핑 규칙을 뽑은 뒤, 규칙 기반으로 나머지 행을 코드로 변환(LLM은 "매핑 설계"만, "대량 데이터 변환"은 결정된 규칙으로 코드가 수행) → 비용/속도/일관성 확보.

## 10. 미해결 질문

- LLM 제공자/모델(사내 정책상 사용 가능한 모델) — 아직 미정. 본 설계는 "구조화 출력을 반환하는 임의의 LLM 호출"을 추상 인터페이스로 두어 특정 제공자에 종속되지 않게 함.
- 민감 데이터(단가, 설비 사양 등)가 외부 LLM API로 전송되는 것에 대한 보안/컴플라이언스 검토 필요 — 사내망 배포형 모델 사용 여부 확인 필요.
