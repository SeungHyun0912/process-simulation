# 07. Meta Schema / 공정 흐름 표현력 검토

> P0~P4 구현을 마친 시점에서, "이 스키마로 실제 복잡한 공정을 얼마나 표현할 수 있는가"를 감사한 결과. 코드 변경 없이 조사만 수행했다.
>
> **추가 검토(6장)**: 3-5(멀티 제품 자원 경합)에 대한 구체적 해결 방향 — "여러 완제품이 같은 원자재를 가공하는 1번 공정을 거친 뒤, 서로 다른 완제품으로 갈라져 다시 합쳐지지 않는" 구체적 케이스를 검토해달라는 요청에 답하며 B안(공유 네트워크 + Routing-Product Link)을 구성했다. 코드 변경은 아직 안 함 — 설계만.
>
> **구현 현황**: 3-1(co-product 비율 분기)과 3-2(merge 비대칭 소비)는 **Phase A로 구현 완료**됐다 — `ProcessStepOutput` 테이블(스텝의 산출물을 별도 테이블로 분리)과 `ProcessStepTransition.output_item_id`/`consumption_ratio` 필드로 반영했다. 4장 원안 대비 `process_step_input`(신규 테이블)은 만들지 않고 그 역할을 `ProcessStepTransition.consumption_ratio`로 흡수하는 방향으로 단순화했다(자세한 근거는 승인된 구현 계획 참고, 세션 로컬 경로 `C:\Users\A00220260124\.claude\plans\floating-toasting-hopper.md`). **3-5/6장(`RoutingProductLink`, 멀티 제품 공유 네트워크)도 Phase B로 구현 완료**됐다 — 알려진 제약 하나: primary 링크의 terminal은 항상 "전체 그래프 실시간 계산"이라, primary 제품 본인의 `scope=product` 조회는 (다른 제품이 포크해간 분기를 포함해도) 항상 전체 네트워크를 보여준다. 그래서 `BLOCK_ORPHAN_TERMINAL_STEP` 게이트는 지금 조건에서는 사실상 발동하지 않는다 (코드 주석에 명시). 실사용에서 문제가 되면 "primary = 전체" 대신 "primary = 포크되지 않고 남은 나머지"로 다듬어야 한다.

## 1. 결론 먼저

**선형 흐름, 병렬 라인 분산(같은 자재를 여러 동일 라인에), 병합(여러 선행 코어를 하나로 합류), 배치 처리**까지는 지금 스키마·컴파일러·시뮬레이터로 표현되고 실행된다 (P3 문서의 5-스텝 케이블 라인 예시로 검증됨).

**하지만 아래 질문의 예시 — "A설비에 1번 자재를 넣으면 1-1과 1-2가 6:4 비율로 나온다" — 는 지금 표현할 수 없다.** 이건 하나의 필드가 빠진 문제가 아니라, `ProcessStep`/`ProcessStepTransition`/컴파일러/시뮬레이터 네 군데 모두가 "1 스텝 = 1 입력 품목 = 1 출력 품목"이라는 전제로 설계되어 있기 때문이다.

## 2. 이미 알고 있던 제약 (의도적으로 미룸, 새 발견 아님)

P2/P3 구현 당시 이미 문서에 남긴 것들 — 재확인만:

- 재작업/불량 흐름(rework/scrap) — `enable_rework_flow`, `quality_binding.enable_quality_logic` 모두 v1 기본값 false, `rework_route_path`/`scrap_route_path`는 스펙상 `null`
- 확률적 처리시간(분포) — `stochastic_defaults.distribution_mode: "deterministic"`
- 교대/캘린더 — `use_workforce_calendar: false`, 24x7 가정

## 3. 이번 검토에서 새로 발견한 것

### 3-1. Co-product 비율 분기 불가 (질문의 핵심 예시) — **Phase A로 해결됨**

- `ProcessStep`(`app/models/process_routing.py:29-59`)의 `output_item_id`는 **단일 문자열**이다. 한 스텝이 "1-1"과 "1-2"를 동시에 낳는 것 자체를 표현할 방법이 없다.
- `ProcessStepTransition`(같은 파일 67-78행)에는 `to_step_no`/`condition`만 있고 **비율(ratio) 필드가 아예 없다.**
- 실행 시(`app/services/simulation.py:103`) 후속 스텝이 여럿이면 무조건 `qty / len(succs)` — **균등 분배만** 가능하다. 6:4처럼 비대칭 비율은 코드 구조상 낼 수 없다.
- 흥미로운 점: 이 기능은 스펙 문서에는 이미 예견돼 있었다. `docs/schema/simpy-schema-compiler.json:163`의 `transition_compilation_rules.split_rule`이 `"branch by condition or configured ratio"`라고 "설정 가능한 비율"을 명시했고, `allowed_flow_types`(`process-simpy-map.json`)에도 `"split"`이 네 번째 값으로 들어 있다. **하지만 실제로 이 비율을 담을 필드가 COMMON_FIELD_DICTIONARY 어디에도 정의된 적이 없고, 컴파일러·시뮬레이터 어디에도 `"split"`이라는 문자열 자체가 등장하지 않는다** — `flow_type: "split"`을 넣어도 지금은 그냥 `"sequential"`과 똑같이 처리된다. 즉 "설계는 예견, 구현은 누락"된 케이스였다.
- **Phase A 구현**: `ProcessStepOutput`(step_id, output_item_id, output_ratio, unit)으로 스텝의 산출물을 1:N으로 분리하고, `ProcessStepTransition.output_item_id`로 어떤 전이가 어떤 산출물을 나르는지 명시. 시뮬레이터는 산출물별로 `qty * output_ratio`를 계산해 해당 산출물을 나르는 전이들에 분배한다.

### 3-2. Merge(합류)도 항상 1:1 소비만 가능 — **Phase A로 해결됨**

`simulation.py:120-124` — merge 스텝은 선행 분기마다 정확히 `1`단위(배치 스텝이면 `1배치`)씩 **똑같이** 소비했다. "심선 2가닥 + 테이프 1개 → 케이블 코어 1개" 같은 비대칭 BOM(자재소요량)은 표현이 안 됐다. 3-1과 사실상 같은 근본 원인(비율 필드 부재)의 반대쪽 증상.

**Phase A 구현**: 별도 `process_step_input` 테이블 대신 `ProcessStepTransition.consumption_ratio`로 흡수 — merge 타깃으로 들어오는 각 전이가 "1 결합 산출 단위당 몇 단위를 소비하는지"를 갖는다. 비대칭 소비는 특정 선행 엣지의 속성이라, 이미 그 엣지를 모델링하는 transition에 두는 게 더 자연스럽다는 판단.

### 3-3. Recipe의 수율/로스 필드가 "죽은 데이터"

`docs/schema/process-schema.json`의 레시피 템플릿에는 이미 `length_factor: {input_per_output, loss_rate}`가 정의돼 있고, `Recipe` 모델(`app/models/recipe.py:18`)에도 `length_factor` JSON 컬럼이 실제로 존재한다. **그런데 컴파일러(`compiler.py`)도 시뮬레이터(`simulation.py`)도 `Recipe`를 아예 참조하지 않는다.** P1에서 Recipe CRUD API는 만들었지만, ProcessStep과 실제로 연결(FK)되어 있지 않아서 "이 스텝은 이 레시피를 쓴다"는 관계 자체가 없다. 수율/로스율 데이터를 입력해도 시뮬레이션 결과에 전혀 반영되지 않는다.

### 3-4. setup_time이 "스텝당 평생 1회"로 고정

`simulation.py:113, 138-139` — `setup_remaining`을 프로세스 시작 시 한 번만 초기화하고, 첫 사이클에서 소진되면 그걸로 끝이다. 실제 공장에서는 같은 설비에서 **제품/레시피가 바뀔 때마다** 셋업(교체) 시간이 반복 발생하는데, 지금은 "이 스텝이 시뮬레이션 내내 한 번도 셋업을 다시 안 한다"고 가정한 것과 같다. 다품종 생산 라인을 표현하려면 이 부분도 손봐야 한다.

### 3-5. 여러 제품이 같은 설비를 두고 실제로 경쟁하는 상황을 표현 못함

`app/api/routes/simulation_runs.py`는 `compile_run` 하나(=제품 하나의 라우팅 하나)를 받아 `run_simulation()`을 호출하고, 그 안에서 `simpy.Environment`/`Resource`가 매번 새로 생성된다(`simulation.py:79, 90`). 제품 A와 제품 B가 실제로는 같은 `GRP-EXT` 설비를 나눠 쓰는 상황이라도, 두 제품을 각각 컴파일·시뮬레이션하면 **서로의 존재를 전혀 모른 채 각자 자원을 통째로 차지한 것처럼 계산된다.** 지금 이 아키텍처는 "제품 1개짜리 라인"을 검증하는 데는 맞지만, **여러 제품이 공유 설비를 놓고 경쟁하는 실제 공장 전체의 용량 시뮬레이션에는 쓸 수 없다.** 이건 필드 하나를 추가해서 될 문제가 아니라, "여러 compiled_graph_object를 하나의 SimPy 환경에 합쳐 실행"하는 새로운 실행 모드가 필요한, 지금까지 발견한 것 중 가장 구조적인 갭이다. → 6장에서 해결 방향(B안)을 설계함, Phase B로 구현 예정.

### 3-6. transition의 condition은 저장만 되고 실행에 반영 안 됨

`simulation.py` 모듈 docstring에 이미 명시된 대로, condition 문자열은 컴파일러에서 그대로 통과(`compiler.py:128-129`)될 뿐 실행 시 평가되지 않는다. 이건 3-1(비율 기반 분기)과는 다른 문제다 — condition은 "품질 검사 결과에 따라 양품/불량 라인으로 갈린다" 같은 **동적·조건부 라우팅**이고, 3-1은 "항상 6:4로 고정 분배"라는 **정적 비율 분기**다. 둘 다 안 되지만 해결 방법은 다르다.

## 4. 6:4 분기를 표현하려면 — 구체적 스키마 확장안 (Phase A로 구현 완료, 아래는 최초 제안 원문)

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

> **실제 구현은 위 원안을 일부 단순화했다**: `process_step_input` 테이블은 만들지 않고 `ProcessStepTransition.consumption_ratio`로 대체 — 6-3/승인된 구현 계획 참고.

## 5. 우선순위 제안

| 항목 | 심각도 | 이유 | 상태 |
|---|---|---|---|
| 3-1 Co-product 비율 분기 | 높음 | 질문에서 직접 제기한 케이스, 다품종/부산물 공정에서 흔함 | **완료 (Phase A)** |
| 3-5 멀티 제품 자원 경합 | 높음 | "실제 공장 전체 용량"을 보려는 목적과 직결되는데 지금 구조로는 원천적으로 불가 | **완료 (Phase B)** |
| 3-3 Recipe 수율/로스 미연결 | 중간 | 필드는 있으니 컴파일러/시뮬레이터 연결만 하면 됨 — 상대적으로 저비용 | 미착수 |
| 3-2 Merge 비대칭 소비(BOM) | 중간 | 3-1과 같은 근본 원인이라 함께 해결 가능 | **완료 (Phase A)** |
| 3-4 setup_time 1회성 | 낮음~중간 | 다품종 라인이 아니면 영향 적음 | 미착수 |
| 3-6 condition 미평가 | 낮음 | 정적 비율(3-1)로 상당수 케이스 대체 가능, 나머지는 별도 규칙 엔진 필요 | 미착수 |

## 6. 3-5 해결 방향 구성 (B안: 공유 네트워크 + Routing-Product Link)

구체적 케이스: 원자재 A가 1번 공정을 거쳐 2가지 타입으로 분리되고, 그 뒤로는 서로 다른 완제품(SKU)으로 갈라져 다시 합쳐지지 않는다. "완제품 기준으로 역순으로 정의할지, Hierarchy하게 구성할지"에 대한 결론: **정의(저장)는 원자재→완제품 방향의 공유 그래프(정순, Hierarchy)로 하고, 제품별 조회만 역순 트레이스로 만든다.** 아래는 그 구체적 스키마·컴파일러·시뮬레이터·API 변경안이다.

### 6-1. 왜 "제품별 독립 그래프 유지"(A안)가 아니라 "공유 그래프"(B안)인가

지금 컴파일/실행 경로를 그대로 따라가 보면: `compile_runs.py:37`이 라우팅 1개(`routing_id`)를 `compile_routing()`에 넘겨 `compiled_graph_object` 1개를 만들고, `simulation_runs.py:89`가 그 결과 1개를 `run_simulation()`에 넘긴다. SimPy `env`/`Resource`는 항상 `simulation.py:79,90`에서 **그 컴파일 결과 범위 안에서만** 새로 생성된다. 즉 지금 아키텍처에서 자원 경쟁이 실제로 반영되는 유일한 조건은 "경쟁하는 스텝들이 같은 `compiled_graph_object.nodes`에 함께 들어 있는 것"이다.

- **A안**(제품별 독립 라우팅 유지)으로 이걸 얻으려면 "여러 `routing_id`를 입력받아 하나의 `compiled_graph_object`로 합성하는 멀티-라우팅 컴파일러"를 **새로 만들어야** 한다 — 지금 없는 기능이고, 만드는 순간 사실상 아래 B안의 `routing_id` 공유를 재발명하는 셈이다.
- **B안**은 애초에 경쟁하는 상류 스텝을 여러 제품이 **같은 `routing_id` 하나** 안에 두는 것이므로, 지금 있는 컴파일러/시뮬레이터를 그대로 호출하면 경쟁이 이미 반영된다. 새 실행 모드가 필요 없다.

### 6-2. 스키마 변경 — 놀랍게도 매우 작다

핵심 발견: `ProcessStep`(`app/models/process_routing.py:29`)에는 `product_id`가 없다. `product_id`는 오직 부모인 `ProcessRouting`에만 있다(`process_routing.py:14`). 즉 **스텝 정의 자체는 이미 "네트워크 네이티브"**다 — 바꿔야 하는 건 "라우팅 1개 = 제품 1개"라는 지금의 1:1 가정 하나뿐이다.

```python
class RoutingProductLink(TimestampMixin, Base):
    """하나의 ProcessRouting(=공유 네트워크)을 여러 제품이 서로 다른
    entry/terminal 구간으로 소비할 수 있게 하는 N:M 연결."""

    __tablename__ = "routing_product_link"
    __table_args__ = (UniqueConstraint("routing_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    routing_id: Mapped[int] = mapped_column(
        ForeignKey("process_routing.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("product.product_id"), index=True)
    entry_step_no: Mapped[str] = mapped_column(String(32))
    terminal_step_nos: Mapped[list] = mapped_column(JSON)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
```

`process_routing.product_id`와 `UniqueConstraint("product_id", "version")`(`process_routing.py:11,14`)는 **그대로 유지**한다 — 의미만 "이 그래프를 최초로 만든/대표하는 제품"으로 좁힌다. 기존 라우팅 전부에 `is_primary=True`인 `RoutingProductLink` 1건을 시딩하는 마이그레이션 한 번으로 하위호환 100% 유지(기존 API 동작 무변화). 포크가 필요해지는 시점에만 두 번째 링크 행을 추가한다: `(routing_id=R1, product_id="Y", entry_step_no="1", terminal_step_nos=["4B"])`.

> **구현 계획에서의 보강**: `entry_step_no`는 복수(`entry_step_nos: list[str]`)로, primary 링크의 entry/terminal은 저장하지 않고 항상 실시간 계산하는 것으로 다듬었다 — 승인된 구현 계획 참고.

### 6-3. 포크 지점은 이미 표현 가능 — 단, 3-1과 묶어야 완성됨

`ProcessStepTransition`은 이미 한 스텝에서 여러 `to_step_no`를 허용한다(`process_routing.py:62`, 1:N `next_steps`). "스텝 1 → 2A 또는 2B" 분기 자체는 지금도 만들 수 있다. 문제는 3-1과 정확히 같았다: 스텝 1의 `output_item_id`가 단일값이라 "2A로 가는 흐름"과 "2B로 가는 흐름"이 서로 다른 품목이라는 걸 표현할 방법이 없고, 실행 시(`simulation.py:96-105` `put_downstream`)도 무조건 균등분배(`share = qty / len(succs)`, 103행)뿐이라 6:4 같은 비율을 낼 수 없었다.

**따라서 3-1과 이번 6장은 함께 구현해야 이번 케이스가 완성된다.** 3-1 수정이 "물리적으로 어떻게 나뉘는가"를, 이번 6장이 "나뉜 뒤 어느 제품 소유가 되는가"를 담당하는 관계다. **3-1은 Phase A로 완료됐고, 6장(Phase B)이 그 위에 얹힌다.**

### 6-4. 컴파일러/검증 변경

`compiler.py`:
- `compile_routing`(59행)의 `product = db.query(Product)...`(79행)을 `links = db.query(RoutingProductLink).filter_by(routing_id=routing.id).all()`로 바꾼다.
- `compiled_graph_object["product_context"]`(179-183행, 지금 단일 dict)를 `product_contexts: [...]`(리스트, 항목마다 `product_id`/`product_name`/`unit`/`entry_step_no`/`terminal_step_nos`)로 바꾼다. **`nodes`/`transitions`/`resource_bindings`/`processing_time_plan`/`queue_plan`은 전혀 안 바뀐다** — 여전히 라우팅 전체를 한 번 순회해서 만드는 그대로다.
- `graph_summary`(184행 이하)에 `linked_product_ids: [...]`를 추가한다 — 몇 개 제품이 이 네트워크를 공유하는지 한눈에 보이게.

`routing_validation.py`(`build_validation_report`, 15행)에 신규 게이트 추가:
- `BLOCK_UNRESOLVED_LINK_STEP`: `RoutingProductLink.entry_step_no`/`terminal_step_nos`가 실제 `step_nos`에 없으면 차단.
- `BLOCK_ORPHAN_TERMINAL_STEP`(신규 발견): `next_steps`가 없는 종단 스텝인데 어떤 링크의 `terminal_step_nos`에도 안 잡혀 있으면 차단 — "만들어놓고 아무 제품도 안 가져가는 브랜치"를 잡는, 지금은 존재하지 않는 무결성 검사.

`app/models/compile_run.py`의 `product_id`(21행, NOT NULL)는 nullable로 완화하거나 `bound_product_ids: JSON` 리스트로 교체한다. `compile_runs.py:42`의 `product_id=routing.product_id`도 함께 수정.

### 6-5. 시뮬레이터 변경 — 최소

이게 이번 설계의 핵심 근거다: `simulation.py`의 실행 루프(`step_process`/`resources`/`containers`, 79-191행)는 **손댈 필요가 없다.** `resources = {key: simpy.Resource(...) ...}`(90행)가 이미 `compiled_graph_object` 전체를 한 번에 순회해 만들어지므로, 스텝 1의 `equipment_group`을 공유하는 2A/2B 하류가 같은 `compiled_graph_object`에 함께 있기만 하면 **자동으로 경쟁한다.**

필요한 추가는 둘뿐이다:
1. `put_downstream`의 exit 분기(98-102행)에 `"item_id": nodes[from_step_no].get("output_item_id")`를 추가 — 어떤 종단 스텝의 산출인지 사후에 알 수 있게. (**Phase A에서 이미 구현됨** — exit 이벤트에 `item_id` 필드 포함)
2. summary(212-223행)에 `"exit_qty_by_step": {step_no: qty, ...}`를 추가 — 지금은 `exit_qty`가 전체 합산뿐(195행)이라, 스텝별로 쪼개야 API 레이어가 `RoutingProductLink.terminal_step_nos`로 제품별 처리량을 재구성할 수 있다. `resource_utilization`/`bottleneck_step_no`는 그대로 **네트워크 전체 기준**으로 유지한다(이게 안 바뀌는 게 이번 기능의 존재 이유다).

### 6-6. API 변경

- `POST /products/{product_id}/routings`(`process_routings.py:83`) 동작은 **무변화** — 생성 시 내부적으로 `RoutingProductLink(is_primary=True, ...)` 1건을 자동 생성한다(엔트리/터미널은 predecessor/successor가 없는 step_no로 매번 재계산).
- 신규: `POST /products/{product_id}/routings/{version}/link` — 다른 제품이 이 라우팅을 공유 네트워크로 참조하도록 등록. `body: {product_id, entry_step_no, terminal_step_nos}`.
- `GET /products/{product_id}/routings/{version}`(`process_routings.py:99`) 응답은 기본적으로 그 제품의 `RoutingProductLink` 기준 `entry_step_no → terminal_step_nos` 서브그래프만 필터링해서 보여주고, `?scope=network`로 전체 공유 그래프를 볼 수 있게 한다. 이 서브그래프 추출(터미널에서 거슬러 올라가는 역방향 탐색)이 바로 "완제품 기준 역순 조회"가 실제로 구현되는 지점이다.
- `GET /simulation-runs/{id}/results/summary`(`simulation_runs.py:151`)에 `?product_id=` 파라미터를 추가 — `exit_qty_by_step`(6-5)을 해당 제품의 `terminal_step_nos`로 합산해 제품별 throughput/리드타임을 재계산해서 반환한다. `resource_utilization`은 필터링 없이 그대로 반환한다 — 공유 자원이므로 "제품별 가동률"이라는 개념 자체가 없다는 걸 응답 스키마 문서에 명시해 오해를 막아야 한다.

### 6-7. 우선순위 재정리 (5장 갱신) — Phase A/B 모두 구현 완료

| 항목 | 심각도 | 구현 순서 제안 | 상태 |
|---|---|---|---|
| 3-1 Co-product 비율 분기(`process_step_output`) | 높음 | 1순위 — 이게 없으면 6장 전체가 무의미 | **완료** |
| 3-5 멀티 제품 자원 경합(`RoutingProductLink`, 6-2/6-4/6-5/6-6) | 높음 | 2순위 — 3-1 위에 얹는 얇은 레이어라 3-1 직후 바로 착수 가능 | **완료** |
| 3-3 Recipe 수율/로스 미연결 | 중간 | 그대로 | 미착수 |
| 3-2 Merge 비대칭 소비 | 중간 | 3-1과 같은 테이블(`process_step_input`)로 함께 처리 → 실제로는 `consumption_ratio`로 흡수 | **완료** |
| 3-4 setup_time 1회성 | 낮음~중간 | 그대로 | 미착수 |
| 3-6 condition 미평가 | 낮음 | 그대로 | 미착수 |

**Phase B 구현에서 확인된 사항**:
- `entry_step_no`(단수)는 계획 단계에서 이미 `entry_step_nos`(복수, JSON 리스트)로 보강해서 구현했다 — 공통 조상 없는 진입점이 여러 개인 서브그래프도 지원.
- primary 링크의 entry/terminal은 정말로 저장하지 않고 매번 실시간 계산한다(`_live_entry_terminal_steps`) — 닭-달걀 문제 해결.
- `compile_run.product_id`(단일)는 `bound_product_ids`(리스트)로 교체했다.
- **알려진 제약**: primary 링크의 terminal이 항상 "전체 그래프"이기 때문에, primary 제품 자신의 `scope=product` 조회 결과가 다른 제품이 포크해간 분기까지 포함한다(교차검증 E2E 테스트에서 실제로 확인됨 — X는 2A+2B 둘 다, Y는 2B만). 물리적으로 "이 제품만의 것"을 보고 싶다면 primary 제품도 명시적으로 `/link`를 통해 자기 자신의 좁은 범위를 다시 등록해야 하는데, 지금은 제품당 링크 1개 제약(`UniqueConstraint(routing_id, product_id)`)이 이를 막는다. 실사용에서 필요해지면 이 제약을 풀거나 "primary = 포크되지 않은 나머지"로 알고리즘을 바꿔야 한다.
