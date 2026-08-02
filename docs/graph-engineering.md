# Graph Engineering / 圖工程

## English

### The shape of the flow is itself a governed object

The workflow is a directed graph, not a pipeline. Before this layer existed
that graph lived in two places that nothing compared: the `transitions` mapping
in the config, and an ASCII drawing in `docs/state-machine.md`. Anyone could add
a transition that created a dead end, an unreachable state, or a brand new
unbounded loop, and every check in the repo would still pass.

Graph Engineering makes the topology machine-checked.

### Graph invariants

All five are declared in `config/governance.yaml` under `graph.invariants` and
enforced by `scripts/validate_governance.py`.

| Invariant | Rule |
| --- | --- |
| `require_all_states_reachable` | Every state is reachable from `NEW` |
| `require_terminal_reachable_from_all` | Every state can still reach a terminal state |
| `require_terminal_states_are_sinks` | `PASSED` and `REJECTED` have no outgoing edges |
| `require_every_cycle_declared` | Every simple cycle matches a declared loop path |
| `require_edge_guards` | Every edge declares a `guard` and `required_evidence` |

The second invariant is the one that catches traps: a state you can enter but
never finish from. The fourth is the load-bearing link to Loop Engineering.

### Every cycle must be declared

The validator enumerates all simple cycles in `workflow.transitions`, rotates
each to a canonical starting state, and requires an exact match against the
paths declared in `loops`. A cycle with no declaration is a governance
violation, not a warning.

This is what makes the rule enforceable rather than aspirational. Adding
`PASSED: [EXECUTIVE]` to the transitions produces three errors at once — a
terminal state that is no longer a sink, a graph edge with no guard, and an
undeclared cycle — without anyone having to notice the change in review.

Declaring a fake path does not launder a real cycle either: each declared path
is separately checked segment by segment against the actual transitions, so a
path that is not a real route fails on its own terms while the real cycle
remains undeclared.

### Cycles in the current graph (English)

There are exactly four, all declared in `loops`:

```text
EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> EXECUTIVE
EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> LEGISLATIVE -> EXECUTIVE
EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> REWORK -> EXECUTIVE
EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> LAW_AMENDMENT_REQUEST -> LEGISLATIVE -> EXECUTIVE
```

### Edges carry guards and evidence

`graph.edges` mirrors `workflow.transitions` exactly — the validator reports
both directions of mismatch — but adds a `guard` and a `required_evidence` to
each of the 14 edges. A transition with no stated condition is a routing
decision nobody can review.

Where a state fans out, the guards must be mutually exclusive. `REWORK` is the
worked example: it routes to `EXECUTIVE` under `rework_budget_remaining` and to
`REJECTED` under `rework_budget_exhausted`.

This is enforced twice rather than asserted once. The validator checks that
every declared `guard` has an implementation in `runtime/guards.py`, so an edge
nothing can ever take fails before it ships. The executor then refuses to route
when more than one guard on a fan-out is satisfied, because picking one would
make the flow depend on dictionary ordering. See
[Case execution](case-execution.md).

### Role isolation as a graph property (English)

Edges that cross a role boundary are handoffs, and each one names the artifact
that crosses with it. `EXECUTIVE -> HARNESS_SUBMITTED` hands over the
`evidence_bundle`; `JUDICIARY -> REWORK` hands back `failure_mode_notes`. The
roles never read each other's private reasoning, so the declared evidence is the
entire contract between them.

## 繁體中文

### 流程的形狀本身就是治理對象

工作流程是一張有向圖，不是一條管線。在這一層存在之前，這張圖存在於兩個
沒有任何東西比對過的地方：config 裡的 `transitions` 對映，
以及 `docs/state-machine.md` 裡的 ASCII 圖。
任何人都可以加入一條造成死路、不可達狀態，或全新無界迴圈的轉換，
而 repo 裡所有檢查依然會通過。

圖工程讓拓撲變成可被程式檢查的東西。

### 圖不變式

五條全部宣告在 `config/governance.yaml` 的 `graph.invariants`，
並由 `scripts/validate_governance.py` 強制執行。

| 不變式 | 規則 |
| --- | --- |
| `require_all_states_reachable` | 所有狀態都能從 `NEW` 抵達 |
| `require_terminal_reachable_from_all` | 所有狀態都還能走到終局狀態 |
| `require_terminal_states_are_sinks` | `PASSED` 與 `REJECTED` 沒有出邊 |
| `require_every_cycle_declared` | 每個簡單環都對應一條已登記的迴圈路徑 |
| `require_edge_guards` | 每條邊都要宣告 `guard` 與 `required_evidence` |

第二條專門抓陷阱狀態：進得去、卻永遠結不了案。
第四條則是與迴圈工程之間的承重連結。

### 每個環都必須登記

驗證器會列舉 `workflow.transitions` 中所有簡單環，
將每個環旋轉到固定的起始狀態，再與 `loops` 中宣告的路徑做精確比對。
沒有登記的環是治理違規，不是警告。

這正是這條規則可被強制而非流於口號的原因。
在 transitions 加入 `PASSED: [EXECUTIVE]` 會同時產生三個錯誤 ——
終局狀態不再是終點、圖上多了一條沒有 guard 的邊、出現未登記的環 ——
不需要任何人在審查時剛好注意到這個改動。

宣告一條假路徑也無法漂白真實的環：
每條宣告路徑都會逐段對照真實轉換分別檢查，
因此不存在的路線會以自己的名義失敗，而真正的環仍然是未登記狀態。

### 目前圖中的環（繁體中文）

正好四個，全部已登記在 `loops`：

```text
EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> EXECUTIVE
EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> LEGISLATIVE -> EXECUTIVE
EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> REWORK -> EXECUTIVE
EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> LAW_AMENDMENT_REQUEST -> LEGISLATIVE -> EXECUTIVE
```

### 邊要帶著 guard 與證據

`graph.edges` 必須與 `workflow.transitions` 完全對應 ——
驗證器會回報兩個方向的不一致 ——
但額外為 14 條邊各自加上 `guard` 與 `required_evidence`。
沒有寫明條件的轉換，等於一個沒有人能審查的路由決策。

當一個狀態有多條出邊時，guard 必須互斥。
`REWORK` 是標準範例：在 `rework_budget_remaining` 時走向 `EXECUTIVE`，
在 `rework_budget_exhausted` 時走向 `REJECTED`。

這件事被強制了兩次，而不是只被主張一次。
驗證器會檢查每個宣告的 `guard` 在 `runtime/guards.py` 都有實作，
所以一條永遠不可能被走到的邊，在出貨前就會失敗。
執行器則會在同一個 fan-out 上有超過一個 guard 成立時拒絕路由，
因為挑其中一條等於讓流程取決於字典順序。
詳見[案件執行](case-execution.md)。

### 角色隔離也是一種圖性質（繁體中文）

跨越角色邊界的邊就是交接，每一條都寫明了跟著一起交出去的證據。
`EXECUTIVE -> HARNESS_SUBMITTED` 交出 `evidence_bundle`；
`JUDICIARY -> REWORK` 交回 `failure_mode_notes`。
各角色永遠不能讀取彼此的私有推理，
因此這些宣告的證據就是它們之間的全部契約。
