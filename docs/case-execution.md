# Case Execution / 案件執行

## English

### The config is the program

`runtime/executor.py` hardcodes no states, no edges, and no ordering. States,
guarded edges, evidence requirements, loop bounds and terminal states are all
read from `config/governance.yaml`, which the validator has already checked.
Changing the governance model is a config change, not a code change.

```python
from runtime import Case, CaseRunner

runner = CaseRunner(config_document)
case = Case("CASE-001", facts={...}, artifacts={...})
result = runner.run(case)

print(result.status.value)  # TERMINAL
print(case.trail())         # NEW -> LEGISLATIVE -> ... -> PASSED
```

### Facts and artifacts are different things

A case carries `facts`, which guards read to decide routing, and `artifacts`,
which are the harness evidence. They are kept apart on purpose: evidence is
what the judiciary reviews, not what the router branches on. Mixing them would
let a case route itself by submitting the right paperwork.

`history` records every hop with the guard that opened it and the evidence that
crossed with it, so a verdict can be reconstructed from the trail alone. A hop
taken because a loop gave out also carries an `escalation` note saying so —
recording only the guard would put a false reason in the trail, since that
guard was never the reason.

### One step

1. If the state is terminal, stop.
2. At `HARNESS_SUBMITTED`, apply the harness gate first. Missing artifacts
   produce the verdict named in `harness.gate_behavior.missing_artifacts`, and
   the case does not move.
3. Evaluate every outgoing edge's guard.
4. Zero satisfied means the case is blocked — legitimate, and reported rather
   than crashed. More than one is refused outright.
5. Check the edge's `required_evidence` is present.
6. Apply loop accounting.
7. Move, and record the hop.

### The harness gate has two verdicts

`gate_behavior` has always named both, but only one was reachable.

**Missing artifacts stop the case.** It cannot leave `HARNESS_SUBMITTED` at
all, and the verdict is `gate_behavior.missing_artifacts`.

**Invalid artifacts do not stop it.** The config says invalid evidence means
`REWORK`, and the only lawful route to `REWORK` runs through the judiciary. So
the gate marks what failed and lets the case go be judged. The existing
`law_items_unproven` guard already read `invalid_artifacts`; nothing had ever
filled it.

The practical effect is that a judiciary verdict of "nothing unproven" no
longer passes a case whose evidence says nothing. Before this, an artifact
submitted as `TODO` reached `PASSED`.

Marks are recomputed on every pass, so repairing an artifact clears it and the
rework loop can converge.

### Validity is mechanical, on purpose

`harness.artifact_checks` names checks per artifact; `runtime/checks.py`
implements them; the validator rejects any check with no implementation and any
required artifact with no checks.

| Check | Rejects |
| --- | --- |
| `non_empty` | blank or whitespace |
| `not_placeholder` | `TODO`, `TBD`, `N/A`, `-`, `?` and friends |
| `contains_a_number` | a plan with no quantity in it |

These do not ask whether the evidence proves the law. That is the judiciary's
job, and a second judge here would have no isolation. What belongs at the gate
is the narrow question a machine can answer without reading for meaning.

`contains_a_number` applies to `test_plan` because a plan that states no
threshold cannot be tested against — the repo's own "no vague success criteria"
rule, applied mechanically.

`not_placeholder` rejects an artifact that *is* a placeholder, not one that
mentions the word: "No blockers pending review" passes.

### Roles act; the graph routes

`state_roles` says which role acts in which state. `NEW` is intake and
`HARNESS_SUBMITTED` is a gate rather than a work state, so both declare `null`,
as do the terminal states. A state with no owner cannot produce evidence, so a
case blocked there needs a caller, not another model call.

`RoleAgency` asks the owning role for that state's output, parses the reply as
JSON shaped `{"facts": {...}, "artifacts": {...}}`, and applies it. The
executor takes an agency optionally — with none, it is a pure state machine,
which is what keeps routing testable without a model.

### When a model does not answer in JSON

Models wrap payloads in prose and code fences constantly, so a reply is
salvaged before anything else: the raw text, then any fenced block, then the
outermost braces. That costs no model call and is fully deterministic, so it
runs first.

If nothing can be salvaged, the role is asked again with its own unusable
answer quoted back and an explicit format demand. Only the role's own output is
quoted, so a repair cannot smuggle in material the role may not read.

**A repair is a retry, so it is bounded and declared.** `model_replies.
max_repair_attempts` sets the ceiling, the validator caps it, and a budget of
`0` disables repair entirely. An unbounded repair loop would be exactly the
failure the loop layer exists to prevent, one level down.

Repairs are counted on the case. A role that needed repairing is a fact about
the run, and a silent retry would hide a model drifting off format. After the
budget is spent, an unreadable reply still raises `AgencyError` — a case that
merely stalls would hide the same thing.

Repair recovers the format. It does not widen authority: a repaired reply goes
through `may_write` exactly like the first one.

### Write authority is the other half of isolation

`may_read` has always existed. `may_write` is its counterpart, and without it
letting models fill in a case would hand routing to whichever model spoke last:
a judiciary that can write `unresolved_law_items` is deciding the verdict, and
an executive that could write it would be clearing itself.

So each role owns a disjoint set of keys, and the validator rejects any config
where two roles claim the same one. Shared write authority is shared
authorship — the audit trail would no longer say who decided.

| Role | Owns |
| --- | --- |
| legislative | `law`, `acceptance_criteria`, `clarification_requires_amendment` |
| executive | `open_ambiguity_items`, `ambiguity_notes`, and the harness artifacts |
| judiciary | `unresolved_law_items`, `defective_law_items`, `red_line_violated`, `amendment_reason` |

Overstepping raises rather than being trimmed, and the whole payload is
refused rather than partly applied. A role reaching for another role's key is
precisely the failure this framework exists to catch, so it is loud.

### Guards live in code, names live in config

`config` names a guard; `runtime/guards.py` supplies its meaning. The validator
checks every name in `graph.edges` has an implementation, so an edge nothing can
ever take fails validation instead of surfacing as a case that mysteriously
stalls.

Fan-out guards are written to be exclusive by construction — each branch
excludes the conditions of the branches above it. At `JUDICIARY` the order is
red line, then defective law, then unproven items, then passed. A red line
outranks every other verdict.

Construction is an argument, so the executor still checks: two satisfied guards
on one fan-out raise `NondeterministicRouting`. A test sweeps every fan-out
against a matrix of fact combinations and asserts at most one door ever opens.

### Loop accounting (English)

The first edge of a declared path is that loop's entry edge, so taking it
counts as one iteration. `clarification_loop` declares two paths that share a
first edge, so both feed one counter.

Each entry also appends the loop's `per_iteration_artifact` to a list. If two
consecutive entries carry the same value, the loop has stagnated and escalates
immediately, without waiting for the iteration budget. Counting alone limits
how long a case spins; comparing artifacts is what notices it spinning in
place.

### Escalation cannot teleport

A loop's `escalation_target` is taken only if it is reachable in one legal
transition from the current state. `rework_loop` escalates to `REJECTED`, and
`REWORK -> REJECTED` is a declared edge, so the case moves.
`clarification_loop` escalates to `LAW_AMENDMENT_REQUEST`, which has no edge
from `LAW_CLARIFICATION_REQUEST` — so the run halts with status `ESCALATED` and
names the target instead of jumping to it.

Jumping would violate the same graph invariants the validator enforces. An
escalation that the graph does not permit is a supervision signal for a human,
not a transition.

## 繁體中文

### 設定檔就是程式

`runtime/executor.py` 沒有寫死任何狀態、任何邊、任何順序。
狀態、帶 guard 的邊、證據需求、迴圈上限與終局狀態，
全部從 `config/governance.yaml` 讀取，而那份設定已經先被驗證器檢查過。
改治理模型是改設定，不是改程式。

```python
from runtime import Case, CaseRunner

runner = CaseRunner(config_document)
case = Case("CASE-001", facts={...}, artifacts={...})
result = runner.run(case)

print(result.status.value)  # TERMINAL
print(case.trail())         # NEW -> LEGISLATIVE -> ... -> PASSED
```

### facts 與 artifacts 是兩回事

案件同時帶著 `facts`（guard 讀取它來決定路由）與 `artifacts`（harness 證據）。
兩者刻意分開：證據是給司法權審查的東西，不是路由的分支條件。
把兩者混在一起，等於讓案件可以靠「交對文件」來決定自己往哪走。

`history` 會記錄每一跳、開啟這一跳的 guard，以及隨之交付的證據，
所以光看這條軌跡就能重建整個判決過程。
因為迴圈用盡而發生的那一跳，還會多帶一個 `escalation` 註記說明原因 ——
只記 guard 會在軌跡裡留下一個假的理由，因為那個 guard 根本不是原因。

### 一個 step 做什麼

1. 如果是終局狀態就停止。
2. 在 `HARNESS_SUBMITTED` 先套用 harness gate。
   證據缺漏會產生 `harness.gate_behavior.missing_artifacts` 所指定的結果，
   案件不會前進。
3. 評估所有出邊的 guard。
4. 零個成立代表案件被擋住 —— 這是合法狀況，會被回報而不是丟例外。
   超過一個成立則直接拒絕。
5. 檢查該條邊的 `required_evidence` 是否存在。
6. 進行迴圈計數。
7. 前進，並記錄這一跳。

### Harness gate 有兩種結果

`gate_behavior` 一直都寫了兩種，但只有一種是走得到的。

**證據缺漏會擋住案件。** 它根本離不開 `HARNESS_SUBMITTED`，
結果就是 `gate_behavior.missing_artifacts`。

**證據無效不會擋住它。**
設定寫的是無效證據等於 `REWORK`，
而通往 `REWORK` 唯一合法的路線要經過司法權。
所以 gate 只把失敗的項目標記起來，讓案件去被審判。
既有的 `law_items_unproven` guard 本來就會讀 `invalid_artifacts`，
只是從來沒有任何東西去填它。

實際效果是：司法權判定「沒有未證明的條目」，
不再能讓一個證據空洞的案件過關。
在此之前，一個內容寫著 `TODO` 的 artifact 是可以一路走到 `PASSED` 的。

標記每次都會重新計算，所以修好某個 artifact 就會清掉它的標記，
rework 迴圈因此能夠收斂。

### 有效性檢查刻意只做機械判斷

`harness.artifact_checks` 為每個 artifact 指定檢查，
`runtime/checks.py` 負責實作，
驗證器則會拒絕沒有實作的檢查，以及沒有任何檢查的必要 artifact。

| 檢查 | 擋掉什麼 |
| --- | --- |
| `non_empty` | 空白或只有空格 |
| `not_placeholder` | `TODO`、`TBD`、`N/A`、`-`、`?` 之類 |
| `contains_a_number` | 沒有任何數量的計畫 |

這些檢查不問「證據有沒有證明法律」。
那是司法權的工作，在這裡再放一個法官等於多一個沒有隔離的審查者。
屬於 gate 的，是機器不必讀懂內容就能回答的那個窄問題。

`contains_a_number` 套用在 `test_plan` 上，
因為沒有寫出門檻的計畫無法被驗證 ——
這就是把 repo 自己「禁止模糊成功定義」那條規則機械化。

`not_placeholder` 擋的是「本身就是佔位符」的 artifact，
不是「提到佔位符字眼」的 artifact：
「No blockers pending review」會通過。

### 角色負責行動，圖負責路由

`state_roles` 指定每個狀態由哪個角色行動。
`NEW` 是收件、`HARNESS_SUBMITTED` 是門檻而不是工作狀態，兩者都宣告為 `null`，
終局狀態亦然。
沒有負責角色的狀態無法產生證據，
所以卡在那裡的案件需要的是呼叫端介入，而不是再叫一次模型。

`RoleAgency` 會向該狀態的負責角色索取產出，
把回覆解析成 `{"facts": {...}, "artifacts": {...}}` 形狀的 JSON 並套用。
執行器可以選擇不帶 agency —— 不帶的時候它就是一台純粹的狀態機，
這正是讓路由邏輯能在沒有模型的情況下被測試的原因。

### 當模型不用 JSON 回答時

模型很常把 payload 包在散文和 code fence 裡，
所以會先嘗試搶救：原始文字、任何 fenced 區塊、最外層的大括號。
這不花任何一次模型呼叫，而且完全是決定性的，因此擺在最前面。

如果完全搶救不到，才會再問這個角色一次，
把它自己那份無法使用的回答引述回去，並明確要求格式。
引述的只有該角色自己的輸出，
所以修復不可能夾帶該角色不得閱讀的材料。

**修復就是重試，所以它有上限而且是宣告出來的。**
`model_replies.max_repair_attempts` 設定上限，驗證器會再加一道天花板，
設成 `0` 則完全關閉修復。
沒有上限的修復迴圈，正是迴圈層存在要防止的那種失敗，只是低了一層。

修復次數會記在案件上。
一個需要被修復的角色，是這次執行的一個事實，
安靜地重試會把「模型正在偏離格式」這件事藏起來。
額度用完後，無法解析的回覆仍然會拋出 `AgencyError` ——
只是讓案件停住，同樣會把問題藏起來。

修復救回來的是格式，不是權限：
修復後的回覆一樣要走 `may_write`，跟第一次完全相同。

### 寫入權限是角色隔離的另一半

`may_read` 一直都在，`may_write` 是它的對稱物。
沒有它的話，讓模型填寫案件內容，等於把路由權交給最後發言的那個模型：
能寫 `unresolved_law_items` 的司法權就是在下判決，
而如果行政權也能寫它，那就是自己幫自己脫罪。

因此每個角色擁有一組互不重疊的欄位，
只要有兩個角色宣稱同一個欄位，驗證器就會拒絕。
共享寫入權就是共享作者身分 —— 稽核軌跡將無法說明究竟是誰做的決定。

| 角色 | 擁有 |
| --- | --- |
| 立法權 | `law`、`acceptance_criteria`、`clarification_requires_amendment` |
| 行政權 | `open_ambiguity_items`、`ambiguity_notes`，以及各項 harness 證據 |
| 司法權 | `unresolved_law_items`、`defective_law_items`、`red_line_violated`、`amendment_reason` |

越權會直接拋錯而不是被修剪掉，
而且整份 payload 會被拒絕，不會只套用一部分。
角色伸手去碰另一個角色的欄位，正是這個框架存在的理由，所以它必須很大聲。

### guard 的實作在程式裡，名稱在設定裡

設定檔負責命名 guard，`runtime/guards.py` 負責給它意義。
驗證器會檢查 `graph.edges` 裡的每個名稱都有實作，
所以一條永遠走不到的邊會在驗證階段失敗，
而不是變成一個莫名其妙卡住的案件。

Fan-out 的 guard 以「互相排除」的方式撰寫 ——
每個分支都排除了它上面各分支的條件。
在 `JUDICIARY` 的順序是：紅線、法律瑕疵、條目未證明、通過。
紅線的優先序高於其他所有判決。

「設計上互斥」只是一種論證，所以執行器仍然會實際檢查：
同一個 fan-out 有兩個 guard 成立就會拋出 `NondeterministicRouting`。
有一個測試會用一整組 fact 組合掃過每一個 fan-out，
斷言任何情況下最多只有一扇門是開的。

### 迴圈計數（繁體中文）

宣告路徑的第一條邊就是該迴圈的進入邊，走過它就算一次迭代。
`clarification_loop` 宣告的兩條路徑共用同一條第一邊，所以共用一個計數器。

每次進入也會把該迴圈的 `per_iteration_artifact` 附加到一個清單。
如果連續兩次進入帶的是相同的值，就判定為停滯並立即升級，
不必等迭代額度用完。
數次數只能限制案件可以繞多久，比對證據才能發現它在原地打轉。

### 升級不能瞬間移動

迴圈的 `escalation_target` 只有在「從目前狀態出發、一步合法轉換可達」時才會執行。
`rework_loop` 升級到 `REJECTED`，而 `REWORK -> REJECTED` 是宣告過的邊，所以案件會移動。
`clarification_loop` 升級到 `LAW_AMENDMENT_REQUEST`，
但從 `LAW_CLARIFICATION_REQUEST` 並沒有這條邊 ——
因此執行會以 `ESCALATED` 狀態停下並指出目標，而不是直接跳過去。

直接跳過去會違反驗證器正在強制的那些圖不變式。
圖不允許的升級，是給人看的監督訊號，不是一次狀態轉換。
