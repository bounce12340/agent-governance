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
