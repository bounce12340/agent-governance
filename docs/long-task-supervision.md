# Long-Task Supervision / 長任務監督

## English

The problem this repo tries to solve is not only task correctness.
It also addresses a common long-task failure mode: the main agent keeps working,
but forgets to report progress until the end.

### Design goals

- keep long tasks visible
- require periodic progress pings
- escalate missed check-ins instead of silently stalling
- preserve evidence for later review

### Supervision model

A long task should be broken into checkpoints.
Each checkpoint should include:

- completed work
- blocked items
- next step
- ETA

### Escalation rule

If a checkpoint is missed:

1. mark the task as overdue
2. request a clarification update
3. if it keeps missing, escalate to rework or clarification
4. after the configured miss limit, stop treating the task as healthy

### Practical effect

This does not magically make an agent disciplined.
It makes discipline enforceable.
The workflow no longer depends on the main agent remembering to be polite.
It depends on the system requiring check-ins.

### How it is enforced (English)

`runtime/supervision.py` implements the rules `long_task` and
`loops.checkpoint_loop` declare.

**The clock is always an argument, never a hidden call.** A supervisor that
reads the wall clock internally cannot be tested, and an untested supervision
rule is the same kind of unbacked claim this layer exists to retire. Pass
`--now` to any command to replay or audit against a fixed time.

**A report missing a field is not a report.** Every name in
`require_progress_summary` must be present and non-empty. The reasoning is the
harness gate's: a check-in that omits `blocked` or `eta` looks like progress
while withholding exactly the part that would show there is none.

**Misses are derived, not incremented.** The count comes from elapsed time
against the deadline, so reviewing a case twice cannot inflate it. A checkpoint
is on time up to and including `last + interval + grace`; each further interval
past that adds one miss.

**Repeating the previous report is stagnation.** Two identical consecutive
summaries escalate immediately, without waiting for the miss ceiling — the same
rule the other three loops use.

### Escalation is the executive raising its hand (English)

Supervision does not move the case. Over the miss ceiling it writes an open
ambiguity and a note **with the executive role's own authority**, and the
case's existing guards route it to `LAW_CLARIFICATION_REQUEST` on the next run.

That target is reachable from `EXECUTIVE` precisely because this is the
executive reporting it cannot proceed. Writing the transition directly would
bypass the graph the validator spends its time protecting, and supervision has
no authority to record a verdict — a supervisor that could write
`red_line_violated` would be judging work it was only meant to watch.

### Commands (English)

```bash
ai-gov case checkpoint --case CASE-001 \
  --completed "auth flow done" --blocked "none" \
  --next-step "storage layer" --eta "2 days"

ai-gov case supervise --case CASE-001
ai-gov case supervise --case CASE-001 --escalate
```

`supervise` exits `0` when healthy, `2` when overdue but inside the ceiling,
and `4` when stagnated or past it. Without `--escalate` it reports and records
nothing, so it is safe to run on a schedule.

## 繁體中文

這個 repo 想解的，不只是任務做得對不對。
它也在處理一個很常見的長任務失敗模式：main agent 明明還在做事，卻常常忘了回報進度，直到最後才一次交代。

### 設計目標

- 讓長任務保持可見
- 強制週期性進度回報
- 漏報時升級處理，而不是默默卡住
- 保留之後可回顧的證據

### 監督模型

長任務應該被切成 checkpoint。
每個 checkpoint 至少要包含：

- 已完成事項
- 阻塞事項
- 下一步
- ETA

### 升級規則

如果 checkpoint 漏報：

1. 先把任務標成逾期
2. 要求補回報
3. 持續漏報就升級成澄清或返工
4. 超過設定次數後，不再把它視為健康任務

### 實際效果

這不會神奇地讓 agent 變自律。
但它可以讓自律變成制度。
流程不再依賴 main agent 自己想起來要回報，而是由系統強制要求回報。

### 實際上如何強制（繁體中文）

`runtime/supervision.py` 實作了 `long_task` 與 `loops.checkpoint_loop` 宣告的規則。

**時鐘永遠是參數，不是藏在裡面的呼叫。**
一個自己去讀系統時間的監督器無法被測試，
而沒有被測試過的監督規則，正是這一層要淘汰的那種空頭主張。
任何指令都可以帶 `--now` 來針對固定時間做重播或稽核。

**缺欄位的回報不算回報。**
`require_progress_summary` 裡的每個名稱都必須存在且非空。
理由跟 harness gate 一樣：
少了 `blocked` 或 `eta` 的回報看起來像有進度，
卻剛好把「其實沒有進度」的那一部分藏起來了。

**漏報次數是推導出來的，不是累加的。**
次數由「經過時間對上期限」計算，所以同一個案件檢查兩次不會讓數字膨脹。
在 `last + interval + grace`（含）之前都算準時，
超過之後每多一個 interval 就多算一次漏報。

**重複上一次的回報就是停滯。**
連續兩次相同的進度摘要會立即升級，不必等漏報次數用完 ——
跟另外三個迴圈用的是同一條規則。

### 升級是行政權自己舉手（繁體中文）

監督不會移動案件。
超過漏報上限時，它會**以行政權自己的權限**寫入一筆未解決的模糊與說明，
案件既有的 guard 會在下一次執行時把它導向 `LAW_CLARIFICATION_REQUEST`。

那個目標之所以從 `EXECUTIVE` 可達，
正是因為這件事本質上就是行政權回報自己無法繼續。
直接寫入狀態轉換會繞過驗證器一直在保護的那張圖，
而且監督沒有下判決的權限 ——
一個能寫 `red_line_violated` 的監督器，
就是在審判它原本只該旁觀的工作。

### 指令（繁體中文）

```bash
ai-gov case checkpoint --case CASE-001 \
  --completed "auth flow done" --blocked "none" \
  --next-step "storage layer" --eta "2 days"

ai-gov case supervise --case CASE-001
ai-gov case supervise --case CASE-001 --escalate
```

`supervise` 在健康時結束碼 `0`，逾期但仍在上限內為 `2`，
停滯或超過上限為 `4`。
不帶 `--escalate` 時它只回報、不寫入任何東西，所以可以安心排程定期執行。
