# Loop Engineering / 迴圈工程

## English

### Why loops need governance

A retry without an exit condition is not resilience. It is an unbounded loop
that nobody has noticed yet.

Before this layer existed, the framework bounded exactly one loop
(`constitution.max_rework_count`) and left the other three unbounded. It also
counted attempts without ever asking whether an attempt made progress. Three
identical submissions burned the whole retry budget and still looked like work.

Loop Engineering makes every repeating path a named, bounded, convergent loop
that leaves evidence on each pass.

### Loop contract

Every loop in `config/governance.yaml` declares:

| Field | Meaning |
| --- | --- |
| `scope` | `graph` for a cycle in the workflow graph, `supervision` for a time-driven loop |
| `paths` | The state cycles this loop covers; empty for `supervision` scope |
| `entry_condition` | What puts a case into this loop |
| `convergence_metric` | The number the loop is trying to drive down |
| `convergence_rule` | How strictly it must fall for the loop to count as converging |
| `exit_condition` | What lets a case leave through the front door |
| `max_iterations` | Hard ceiling on passes |
| `per_iteration_artifact` | Evidence each pass must produce |
| `stagnation_rule` | What counts as no progress |
| `escalation_target` | Where the case goes when the loop fails |

### Counting is not convergence

`max_iterations` alone only limits how long a case can spin. It does not detect
spinning in place. That is what `convergence_metric` and `stagnation_rule` are
for.

The rule this repo uses: if two consecutive passes produce the same
`per_iteration_artifact`, the loop has stagnated and escalates immediately,
without waiting for the iteration budget to run out.

### Three questions, three checks

The metric and the artifact answer different questions, and the bound answers a
third.

| Check | Asks |
| --- | --- |
| `convergence_rule` on `convergence_metric` | did the number the loop exists to reduce actually move the right way? |
| `stagnation_rule` on `per_iteration_artifact` | did the role hand back the same work? |
| `max_iterations` | has this gone on long enough regardless? |

A role can hand back genuinely different paperwork that fixed nothing, which
stagnation detection cannot see. A role can also fix things slowly, which the
bound alone would punish. Each check catches what the others miss.

Convergence is checked first, because a metric that climbed is a stronger
statement than familiar-looking paperwork: the pass left the case worse than it
found it.

| Rule | Means |
| --- | --- |
| `must_not_increase` | a flat pass is tolerated; growth is not |
| `must_strictly_decrease` | every pass must fix something |
| `supervised_elsewhere` | the metric is real, but another layer owns it |

`rework_loop` and `clarification_loop` use `must_not_increase` — three and two
passes respectively is room for a slow one, but never for the count to grow.
`amendment_loop` uses `must_strictly_decrease`: with two passes, an amendment
round that repairs no defective law item has achieved nothing, and it now ends
the loop before the bound would.

`checkpoint_loop` declares `supervised_elsewhere`. Its metric is
`missed_checkpoints`, which the supervisor derives from elapsed time rather
than from anything loop accounting can observe. Saying so is more honest than
running a check that could never fire.

Rules are named in config and implemented in `runtime/convergence.py`; the
validator rejects a rule with no implementation, the same way it does for
guards and artifact checks.

### Counting is still not convergence

Fresh evidence on every pass defeats stagnation detection, and that is exactly
when the bound has to do the work —
`max_iterations` is enforced for every loop, not only the one whose graph
happens to express a budget in its guards.

Where the overflow goes is the graph's decision, for the same reason escalation
cannot teleport. If the escalation target is reachable from the state the case
is entering, the declared guards take it there and the trail shows the route —
`rework_loop` exits that way, through `REWORK -> REJECTED` on
`rework_budget_exhausted`. Only when the graph has no way to express the
overflow does the loop layer halt the run with `ESCALATED`, which is what
`clarification_loop` and `amendment_loop` do.

### Declared loops (English)

#### rework_loop (English)

`JUDICIARY -> REWORK -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY`

Judiciary found unproven law items. Convergence is measured by
`unresolved_law_items`; the loop exits when it reaches zero. Bounded at 3 passes
(equal to `constitution.max_rework_count`), then escalates to `REJECTED`.

#### clarification_loop (English)

`EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> EXECUTIVE` and
`EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> LEGISLATIVE -> EXECUTIVE`

Executive cannot act because the law is ambiguous. Convergence is measured by
`open_ambiguity_items`. Bounded at 2 passes, then escalates to
`LAW_AMENDMENT_REQUEST` — repeated ambiguity is a defect in the law, not in the
execution.

#### amendment_loop (English)

`JUDICIARY -> LAW_AMENDMENT_REQUEST -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY`

Judiciary found the law itself defective. Convergence is measured by
`defective_law_items`. Bounded at 2 passes, then escalates to `REJECTED`.

#### checkpoint_loop (English)

No graph path. This loop is driven by elapsed time, not by state transitions,
so its `scope` is `supervision` and its `paths` list is empty. It bounds missed
checkpoints during long-running work at 2 (equal to
`long_task.max_missed_checkpoints`), then escalates to
`LAW_CLARIFICATION_REQUEST`.

This asymmetry matters: every graph cycle must be a declared loop, but a
declared loop is not required to be a graph cycle.

### What the validator enforces (English)

`scripts/validate_governance.py` checks that every required loop exists, that
all contract fields are present and well-typed, that `max_iterations` is a
positive integer, that `escalation_target` names a real state, that every
segment of every declared path is a real transition and the path closes into a
cycle, and that `rework_loop` and `checkpoint_loop` agree with the constitution
and long-task limits they mirror.

## 繁體中文

### 為什麼迴圈需要治理

沒有退出條件的重試不是韌性，而是還沒被發現的無限迴圈。

在這一層存在之前，這個框架只對一個迴圈設了上限
（`constitution.max_rework_count`），另外三個完全無界。而且它只數次數，
從來不問這次嘗試有沒有進展。連續三次交出一模一樣的東西，重試額度就用完了，
表面上看起來卻像是有在做事。

迴圈工程要求每一條會重複的路徑，都是具名、有界、可收斂，而且每輪留下證據的迴圈。

### 迴圈契約

`config/governance.yaml` 中的每個迴圈都要宣告：

| 欄位 | 意義 |
| --- | --- |
| `scope` | `graph` 表示流程圖上的環，`supervision` 表示時間驅動的迴圈 |
| `paths` | 這個迴圈涵蓋的狀態環；`supervision` 範圍留空 |
| `entry_condition` | 什麼情況會讓案件進入這個迴圈 |
| `convergence_metric` | 這個迴圈想要壓下去的數字 |
| `convergence_rule` | 它必須以多嚴格的方式下降，才算這個迴圈有在收斂 |
| `exit_condition` | 什麼情況可以正常走出去 |
| `max_iterations` | 繞圈次數的硬上限 |
| `per_iteration_artifact` | 每一輪必須產生的證據 |
| `stagnation_rule` | 什麼情況算是沒有進展 |
| `escalation_target` | 迴圈失敗時案件要去哪裡 |

### 數次數不等於收斂

`max_iterations` 只能限制案件可以繞多久，無法偵測原地打轉。
這正是 `convergence_metric` 與 `stagnation_rule` 存在的理由。

本 repo 採用的規則是：如果連續兩輪產生相同的 `per_iteration_artifact`，
就判定為停滯並立即升級，不必等到次數用完。

### 三個問題，三種檢查

指標與證據回答的是不同問題，上限回答的是第三個。

| 檢查 | 問的是 |
| --- | --- |
| `convergence_metric` 上的 `convergence_rule` | 這個迴圈存在要壓低的數字，真的往正確方向動了嗎？ |
| `per_iteration_artifact` 上的 `stagnation_rule` | 角色是不是交回了同樣的東西？ |
| `max_iterations` | 不管怎樣，這是不是已經拖太久了？ |

角色可以交回內容確實不同、卻什麼也沒修好的文件 —— 停滯偵測看不到這件事。
角色也可能只是修得慢，而單靠上限會誤傷這種情況。
三種檢查各自補上另外兩種漏掉的部分。

收斂會被最先檢查，因為「數字往上跑」是比「文件看起來很眼熟」更強的判斷：
這一輪讓案件比進來時更糟。

| 規則 | 意思 |
| --- | --- |
| `must_not_increase` | 容許持平，但不容許成長 |
| `must_strictly_decrease` | 每一輪都必須修好一些東西 |
| `supervised_elsewhere` | 指標是真的，但由另一層負責把關 |

`rework_loop` 與 `clarification_loop` 用 `must_not_increase` ——
三輪與兩輪的額度容得下一次進展緩慢的嘗試，但絕不容許數字往上長。
`amendment_loop` 用 `must_strictly_decrease`：
只有兩輪額度，一次修不掉任何瑕疵條目的修法就是什麼也沒達成，
現在它會在上限用完之前就結束這個迴圈。

`checkpoint_loop` 宣告 `supervised_elsewhere`。
它的指標是 `missed_checkpoints`，由監督層從經過時間推導，
不是迴圈計數看得到的東西。
明講這件事，比放一個永遠不會觸發的檢查誠實。

規則在設定檔裡命名、在 `runtime/convergence.py` 裡實作；
驗證器會拒絕沒有實作的規則，跟 guard 與 artifact 檢查的做法一致。

### 數次數依然不等於收斂

每一輪都交出不同的證據就能躲過停滯偵測，
而那正是上限必須發揮作用的時候 ——
`max_iterations` 對每一個迴圈都會強制，
不是只對那個剛好在 guard 裡表達了預算的迴圈。

溢出要往哪裡去，由圖決定，理由跟「升級不能瞬間移動」一樣。
如果升級目標從案件即將進入的狀態可達，
就由宣告好的 guard 帶它過去，軌跡上也看得到這條路線 ——
`rework_loop` 就是這樣離場的，走 `REWORK -> REJECTED`，
guard 是 `rework_budget_exhausted`。
只有在圖完全無法表達這個溢出時，迴圈層才會以 `ESCALATED` 停下執行，
`clarification_loop` 與 `amendment_loop` 屬於這一種。

### 已登記的迴圈（繁體中文）

#### rework_loop（繁體中文）

`JUDICIARY -> REWORK -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY`

司法權發現有法律條目未被證明。收斂指標是 `unresolved_law_items`，歸零即可離開。
上限 3 輪（等於 `constitution.max_rework_count`），超過則升級為 `REJECTED`。

#### clarification_loop（繁體中文）

`EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> EXECUTIVE` 與
`EXECUTIVE -> LAW_CLARIFICATION_REQUEST -> LEGISLATIVE -> EXECUTIVE`

行政權因法律模糊而無法執行。收斂指標是 `open_ambiguity_items`。
上限 2 輪，超過則升級為 `LAW_AMENDMENT_REQUEST` ——
反覆模糊是法律本身的缺陷，不是執行的問題。

#### amendment_loop（繁體中文）

`JUDICIARY -> LAW_AMENDMENT_REQUEST -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY`

司法權認定法律本身有瑕疵。收斂指標是 `defective_law_items`。
上限 2 輪，超過則升級為 `REJECTED`。

#### checkpoint_loop（繁體中文）

沒有圖上的路徑。這個迴圈由經過時間驅動，而非狀態轉換，
因此 `scope` 是 `supervision`，`paths` 留空。
它限制長任務期間漏報 checkpoint 的次數為 2 次
（等於 `long_task.max_missed_checkpoints`），超過則升級為
`LAW_CLARIFICATION_REQUEST`。

這個不對稱很重要：圖上的每個環都必須是已登記的迴圈，
但已登記的迴圈不一定要是圖上的環。

### 驗證器實際檢查什麼（繁體中文）

`scripts/validate_governance.py` 會檢查必要迴圈是否齊全、契約欄位是否存在且型別正確、
`max_iterations` 是否為正整數、`escalation_target` 是否為合法狀態、
每條宣告路徑的每一段是否都是真實存在的轉換且能閉合成環，
以及 `rework_loop` 與 `checkpoint_loop` 是否與其對應的憲法與長任務上限一致。
