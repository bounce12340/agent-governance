# Governance Cycle Example / 治理流程範例

## English

### Scenario

Build a mobile app in 6 weeks.

### Step 1, Constitution check

The constitution layer is checked before any role begins.

- Privacy is mandatory.
- Red lines cannot be bypassed.
- Harness evidence is required before judgment.

### Step 2, Legislative output

- Define the law.
- Write acceptance criteria.
- State the red lines.
- Define the retry limit.

### Step 3, Executive output

- Implement the core flow.
- Produce screenshots and logs.
- Prepare the harness artifacts.
- Add long-task checkpoints if the work is lengthy.

### Step 4, Harness submission

No judgment can happen before the harness gate is passed.
If the task is long-running, progress checkpoints must also be submitted.

- Submit tests.
- Submit evidence bundle.
- Submit failure mode notes.

### Step 5, Judiciary review

Judiciary can return amendment requests or clarification requests.

- If evidence is incomplete, return INCOMPLETE.
- If law is ambiguous, issue a law amendment request.
- If output fails, return REWORK.
- If red lines are hit, return REJECTED.

### Step 6, Final verdict

- PASSED only if law, evidence, and output all match.

## 繁體中文

### 情境

在 6 週內做出一個 mobile app。

### 第 1 步，憲法檢查

在任何角色開始前，先檢查憲法層。

- 隱私必須存在。
- 紅線不能被繞過。
- 在司法判定前，必須先有 Harness 證據。

### 第 2 步，立法輸出

- 定義法律。
- 寫驗收標準。
- 寫紅線。
- 定義最大重試次數。

### 第 3 步，行政輸出

- 實作核心流程。
- 產出截圖與 logs。
- 準備 harness 證據包。
- 如果是長任務，要另外加 checkpoint。

### 第 4 步，Harness 提交

在通過 harness gate 之前，不能進司法判決。
如果是長任務，還要附上進度 checkpoint。

- 提交測試。
- 提交證據包。
- 提交失敗模式說明。

### 第 5 步，司法審查

司法權可以回傳修法請求或澄清請求。

- 如果證據不完整，回傳 INCOMPLETE。
- 如果法律模糊，提出修法請求。
- 如果輸出失敗，回傳 REWORK。
- 如果踩到紅線，回傳 REJECTED。

### 第 6 步，最終判決

- 只有法律、證據、輸出三者一致，才算 PASSED。
