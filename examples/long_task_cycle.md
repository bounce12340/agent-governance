# Long-Task Cycle Example / 長任務流程範例

## English

### Scenario

A main agent is asked to run a 3-hour research task.

### Required checkpoints

- checkpoint 1: research direction chosen
- checkpoint 2: evidence collected
- checkpoint 3: draft conclusion
- checkpoint 4: final delivery

### Progress ping format

- completed
- blocked
- next step
- ETA

### Failure handling

- missing one checkpoint: request clarification
- missing two checkpoints: mark as rework
- missing more than the limit: reject or escalate

## 繁體中文

### 情境

main agent 被要求跑一個 3 小時的研究任務。

### 必要 checkpoint

- checkpoint 1：確認研究方向
- checkpoint 2：收集證據
- checkpoint 3：草稿結論
- checkpoint 4：最終交付

### 回報格式

- completed
- blocked
- next step
- ETA

### 失敗處理

- 少一次 checkpoint：要求澄清
- 少兩次 checkpoint：標記為 rework
- 超過上限：拒絕或升級處理
