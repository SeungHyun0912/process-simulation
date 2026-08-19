# 06. Meta Schema / 공정 흐름 표현력 검토

> P0~P4 구현을 마친 시점에서, "이 스키마로 실제 복잡한 공정을 얼마나 표현할 수 있는가"를 감사한 결과. 코드 변경 없이 조사만 수행했다.

## 1. 결론 먼저

**선형 흐름, 병렬 라인 분산(같은 자재를 여러 동일 라인에), 병합(여러 선행 코어를 하나로 합류), 배치 처리**까지는 지금 스키마·컴파일러·시뮬레이터로 표현되고 실행된다 (P3 문서의 5-스텝 케이블 라인 예시로 검증됨).

**하지만 아래 질문의 예시 — "A설비에 1번 자재를 넣으면 1-1과 1-2가 6:4 비율로 나온다" — 는 지금 표현할 수 없다.** 이건 하나의 필드가 빠진 문제가 아니라, `ProcessStep`/`ProcessStepTransition`/컴파일러/시뮬레이터 네 군데 모두가 "1 스텝 = 1 입력 품목 = 1 출력 품목"이라는 전제로 설계되어 있기 때문이다.

## 2. 이미 알고 있던 제약 (의도적으로 미룸, 새 발견 아님)

P2/P3 구현 당시 이미 문서에 남긴 것들 — 재확인만:

- 재작업/불량 흐름(rework/scrap) — `enable_rework_flow`, `quality_binding.enable_quality_logic` 모두 v1 기본값 false, `rework_route_path`/`scrap_route_path`는 스펙상 `null`
- 확률적 처리시간(분포) — `stochastic_defaults.distribution_mode: "deterministic"`
- 교대/캘린더 — `use_workforce_calendar: false`, 24x7 가정

## 3. 이번 검토에서 새로 발견한 것

### 3-1. Co-product 비율 분기 불가 (질문의 핵심 예시)

- `ProcessStep`(`app/models/process_routing.py:29-59`)의 `output_item_id`는 **단일 문자열**이다. 한 스텝이 "1-1"과 "1-2"를 동시에 낳는 것 자체를 표현할 방법이 없다.
- `ProcessStepTransition`(같은 파일 67-78행)에는 `to_step_no`/`condition`만 있고 **비율(ratio) 필드가 아예 없다.**
- 실행 시(`app/services/simulation.py:103`) 후속 스텝이 여럿이면 무조건 `qty / len(succs)` — **균등 분배만** 가능하다. 6:4처럼 비대칭 비율은 코드 구조상 낼 수 없다.
- 흥미로운 점: 이 기능은 스펙 문서에는 이미 예견돼 있었다. `docs/schema/simpy-schema-compiler.json:163`의 `transition_compilation_rules.split_rule`이 `"branch by condition or configured ratio"`라고 "설정 가능한 비율"을 명시했고, `allowed_flow_types`(`process-simpy-map.json`)에도 `"split"`이 네 번째 값으로 들어 있다. **하지만 실제로 이 비율을 담을 필드가 COMMON_FIELD_DICTIONARY 어디에도 정의된 적이 없고, 컴파일러·시뮬레이터 어디에도 `"split"`이라는 문자열 자체가 등장하지 않는다** — `flow_type: "split"`을 넣어도 지금은 그냥 `"sequential"`과 똑같이 처리된다. 즉 "설계는 예견, 구현은 누락"된 케이스다.

### 3-2. Merge(합류)도 항상 1:1 소비만 가능

`simulation.py:120-124` — merge 스텝은 선행 분기마다 정확히 `1`단위(배치 스텝이면 `1배치`)씩 **똑같이** 소비한다. "심선 2가닥 + 테이프 1개 → 케이블 코어 1개" 같은 비대칭 BOM(자재소요량)은 표현이 안 된다. 3-1과 사실상 같은 근본 원인(비율 필드 부재)의 반대쪽 증상이다.

### 3-3. Recipe의 수율/로스 필드가 "죽은 데이터"

`docs/schema/process-schema.json`의 레시피 템플릿에는 이미 `length_factor: {input_per_output, loss_rate}`가 정의돼 있고, `Recipe` 모델(`app/models/recipe.py:18`)에도 `length_factor` JSON 컬럼이 실제로 존재한다. **그런데 컴파일러(`compiler.py`)도 시뮬레이터(`simulation.py`)도 `Recipe`를 아예 참조하지 않는다.** P1에서 Recipe CRUD API는 만들었지만, ProcessStep과 실제로 연결(FK)되어 있지 않아서 "이 스텝은 이 레시피를 쓴다"는 관계 자체가 없다. 수율/로스율 데이터를 입력해도 시뮬레이션 결과에 전혀 반영되지 않는다.

### 3-4. setup_time이 "스텝당 평생 1회"로 고정

`simulation.py:113, 138-139` — `setup_remaining`을 프로세스 시작 시 한 번만 초기화하고, 첫 사이클에서 소진되면 그걸로 끝이다. 실제 공장에서는 같은 설비에서 **제품/레시피가 바뀔 때마다** 셋업(교체) 시간이 반복 발생하는데, 지금은 "이 스텝이 시뮬레이션 내내 한 번도 셋업을 다시 안 한다"고 가정한 것과 같다. 다품종 생산 라인을 표현하려면 이 부분도 손봐야 한다.

### 3-5. 여러 제품이 같은 설비를 두고 실제로 경쟁하는 상황을 표현 못함

`app/api/routes/simulation_runs.py`는 `compile_run` 하나(=제품 하나의 라우팅 하나)를 받아 `run_simulation()`을 호출하고, 그 안에서 `simpy.Environment`/`Resource`가 매번 새로 생성된다(`simulation.py:79, 90`). 제품 A와 제품 B가 실제로는 같은 `GRP-EXT` 설비를 나눠 쓰는 상황이라도, 두 제품을 각각 컴파일·시뮬레이션하면 **서로의 존재를 전혀 모른 채 각자 자원을 통째로 차지한 것처럼 계산된다.** 지금 이 아키텍처는 "제품 1개짜리 라인"을 검증하는 데는 맞지만, **여러 제품이 공유 설비를 놓고 경쟁하는 실제 공장 전체의 용량 시뮬레이션에는 쓸 수 없다.** 이건 필드 하나를 추가해서 될 문제가 아니라, "여러 compiled_graph_object를 하나의 SimPy 환경에 합쳐 실행"하는 새로운 실행 모드가 필요한, 지금까지 발견한 것 중 가장 구조적인 갭이다.

### 3-6. transition의 condition은 저장만 되고 실행에 반영 안 됨

`simulation.py` 모듈 docstring에 이미 명시된 대로, condition 문자열은 컴파일러에서 그대로 통과(`compiler.py:128-129`)될 뿐 실행 시 평가되지 않는다. 이건 3-1(비율 기반 분기)과는 다른 문제다 — condition은 "품질 검사 결과에 따라 양품/불량 라인으로 갈린다" 같은 **동적·조건부 라우팅**이고, 3-1은 "항상 6:4로 고정 분배"라는 **정적 비율 분기**다. 둘 다 안 되지만 해결 방법은 다르다.

## 4. 6:4 분기를 표현하려면 — 구체적 스키마 확장안 (제안, 미구현)

가장 깨끗한 방법은 `ProcessStep`의 `output_item_id`(단일값)를 없애고, **스텝의 산출물을 별도 테이블로 분리**하는 것이다.

```
process_step_output            (신규 테이블)
  id, step_no(FK), output_item_id, output_ratio, unit
  예: (step "A", "ITEM-1-1", 0.6, "kg")
      (step "A", "ITEM-1-2", 0.4, "kg")
```

그리고 `ProcessStepTransition`에 "이 전이가 어떤 산출물을 실어 나르는지"를 명시하는 참조를 추가한다.

```
process_step_transition
  ...기존 필드...
  output_item_id  (nullable — 지정하면 그 산출물만 이 경로로, 없으면 스텝의 유일한 산출물)
```

시뮬레이터 쪽에서는 `step_process`가 스텝당 하나의 `qty`만 계산하는 대신, **산출물별로 `qty * output_ratio`를 계산해서 각자의 후속 컨테이너에 넣는 방식**으로 바뀌어야 한다 (지금의 "균등분배" 로직을 대체). Merge의 비대칭 소비(3-2)도 같은 패턴으로 `process_step_input`(consumption_ratio 포함) 테이블을 추가하면 함께 해결된다.

## 5. 우선순위 제안

| 항목 | 심각도 | 이유 |
|---|---|---|
| 3-1 Co-product 비율 분기 | 높음 | 질문에서 직접 제기한 케이스, 다품종/부산물 공정에서 흔함 |
| 3-5 멀티 제품 자원 경합 | 높음 | "실제 공장 전체 용량"을 보려는 목적과 직결되는데 지금 구조로는 원천적으로 불가 |
| 3-3 Recipe 수율/로스 미연결 | 중간 | 필드는 있으니 컴파일러/시뮬레이터 연결만 하면 됨 — 상대적으로 저비용 |
| 3-2 Merge 비대칭 소비(BOM) | 중간 | 3-1과 같은 근본 원인이라 함께 해결 가능 |
| 3-4 setup_time 1회성 | 낮음~중간 | 다품종 라인이 아니면 영향 적음 |
| 3-6 condition 미평가 | 낮음 | 정적 비율(3-1)로 상당수 케이스 대체 가능, 나머지는 별도 규칙 엔진 필요 |

이 중 어느 것부터 실제로 구현할지 결정해주시면 이어서 진행하겠습니다.
