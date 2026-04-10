# Governance Architecture / 治理架構

## English

This repo is built as a five-layer governance system.
Each layer has a different job, a different authority, and a different review boundary.

### 1. Constitution layer

The constitution layer defines global rules that apply to every case.
It answers the question: what is never allowed, no matter what the law says?

Examples:

- no secret leakage
- no personal data leakage
- no bypassing mandatory review
- no self-judging of original reasoning
- no judgment without harness evidence

### 2. Legislative layer

The legislative layer converts a request into law.
It produces the acceptance criteria, metrics, red lines, and evidence requirements.

Output examples:

- `LAW-001`
- acceptance criteria
- red lines
- retry cap

### 3. Executive layer

The executive layer builds the deliverable.
It can only work within the law and constitution.
It produces the actual output plus supporting evidence.

Output examples:

- `CASE-001`
- implementation
- logs
- screenshots
- test artifacts

### 4. Harness layer

The harness layer defines how proof is collected.
It is a hard gate, not a suggestion.
If the evidence bundle is incomplete, the case is not ready for judgment.

Required artifacts:

- test plan
- evidence bundle
- output snapshot
- failure mode notes

### 5. Long-task supervision

Long-running work needs checkpointing.
The main agent should report progress before the task goes silent.

Checkpoint fields:

- completed
- blocked
- next step
- ETA

Escalation path:

- missed checkpoint -> request update
- repeated misses -> clarification request
- repeated misses after limit -> rework or rejection

### 6. Judiciary layer

The judiciary layer checks the output against the law and constitution.
It can:

- pass the case
- reject the case
- request rework
- request a law clarification
- request a law amendment

### Feedback paths

A real governance system needs reverse feedback, not just a one-way pipeline.

- Judiciary -> Legislative: law amendment request
- Executive -> Legislative: clarification request
- Harness -> Judiciary: incomplete evidence notice

### Long-task supervision

Long-running work needs checkpointing.
A main agent that stays silent too long should be treated as a supervision failure.

Recommended checkpoint fields:

- completed
- blocked
- next step
- ETA

Escalation path:

- missed checkpoint -> request update
- repeated misses -> clarification request
- repeated misses after limit -> rework or rejection

### Rework control

Rework is capped to prevent infinite loops.
After the maximum retry count, the case is rejected.

### Role isolation

Each role must stay isolated.
This means separate prompts, separate authority, and separate access to internal reasoning.
A role should not be allowed to audit its own original decision.

## 繁體中文

這個 repo 以五層治理系統來組成。
每一層都有不同工作、不同權限、不同的審查邊界。

### 1. 憲法層

憲法層定義所有案件都必須遵守的全域規則。
它回答的問題是：不管法律怎麼寫，什麼事情永遠不能做？

例如：

- 不能外洩 secret
- 不能外洩個人資料
- 不能跳過必要審查
- 不能自己審自己的原始思路
- 沒有 Harness 證據就不能判決

### 2. 立法層

立法層負責把需求轉成法律。
它產出驗收標準、指標、紅線與證據需求。

輸出範例：

- `LAW-001`
- 驗收標準
- 紅線
- 重試上限

### 3. 行政層

行政層負責把東西做出來。
它只能在法律與憲法內工作。
它會產出真正的結果與證據。

輸出範例：

- `CASE-001`
- 實作內容
- logs
- 截圖
- 測試 artefacts

### 4. Harness 層

Harness 層定義如何收集證據。
它是硬門檻，不是建議。
如果證據包不完整，案件就不能進司法審查。

必備項目：

- test plan
- evidence bundle
- output snapshot
- failure mode notes

### 5. 長任務監督

長任務需要 checkpoint。
main agent 不能一直做事卻不回報。

checkpoint 欄位：

- completed
- blocked
- next step
- ETA

升級路徑：

- 漏報 checkpoint -> 要求補回報
- 持續漏報 -> 澄清請求
- 超過上限仍漏報 -> 返工或拒絕

### 6. 司法層

司法層負責把輸出和法律、憲法逐條比對。
它可以：

- 通過案件
- 拒絕案件
- 要求返工
- 要求法律澄清
- 要求法律修正

### 回饋路徑

真正的治理系統需要反向回饋，而不只是單向流程。

- 司法 -> 立法：法律修正請求
- 行政 -> 立法：澄清請求
- Harness -> 司法：證據不足通知

### 長任務監督

長任務需要 checkpoint。
如果 main agent 太久沒有回報，就應該視為監督失敗。

建議的 checkpoint 欄位：

- completed
- blocked
- next step
- ETA

升級路徑：

- 漏報 checkpoint -> 要求補回報
- 持續漏報 -> 澄清請求
- 超過上限仍漏報 -> 返工或拒絕

### Rework 控制

Rework 必須設上限，避免無限迴圈。
超過最大重試次數後，案件就會被拒絕。

### 角色隔離

每個角色都必須隔離。
意思是要有不同的 prompt、不同的權限、不同的內部資訊存取。
任何角色都不能審自己的原始決策。
