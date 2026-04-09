# Data Flow and State Machine / 資料流與狀態機

## English

This framework uses a strict flow.
Every task must move through the system in a predictable order.

### Data flow

1. **Input**

   - User request
   - Project constraints
   - Evidence bundle

2. **Legislative stage**

   - Convert the request into laws.
   - Define acceptance criteria, metrics, and red lines.
   - Output: `LAW-XXXX`

3. **Executive stage**

   - Execute only inside the law.
   - Produce deliverables and proof.
   - Output: `CASE-XXXX`

4. **Judiciary stage**

   - Compare output against law and constitution.
   - Approve, reject, or request amendment.
   - Output: `JUDGMENT-XXXX`

### State machine

```text
NEW -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> PASSED
                         \-> LAW_CLARIFICATION_REQUEST <-/
                         \-> LAW_AMENDMENT_REQUEST <-/
                         \-> REWORK -> EXECUTIVE
                         \-> REJECTED
```

### State rules

- `NEW` means the task has not been formalized yet.
- `LEGISLATIVE` means the law is being written.
- `EXECUTIVE` means work is in progress.
- `HARNESS_SUBMITTED` means evidence is ready for review.
- `JUDICIARY` means verification is running.
- `LAW_CLARIFICATION_REQUEST` means the law is too ambiguous for execution.
- `LAW_AMENDMENT_REQUEST` means the law itself needs revision.
- `REWORK` means the task failed review and must be fixed.
- `PASSED` means the task satisfied the law.
- `REJECTED` means the task violated a red line.

### Harness artifacts

Every transition should leave evidence:

- requirement spec
- test cases
- logs
- screenshots
- output files
- final verdict

## 繁體中文

這套框架採用嚴格流轉。
每個任務都必須按照可預期的順序往前走。

### 資料流

1. **輸入**

   - 使用者需求
   - 專案限制
   - 證據包

2. **立法階段**

   - 將需求轉成法律。
   - 定義驗收標準、指標與紅線。
   - 輸出：`LAW-XXXX`

3. **行政階段**

   - 只能在法律框架內執行。
   - 產出交付物與證據。
   - 輸出：`CASE-XXXX`

4. **司法階段**

   - 把輸出和法律、憲法逐條比對。
   - 通過、退回，或要求修法。
   - 輸出：`JUDGMENT-XXXX`

### 狀態機

```text
NEW -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> PASSED
                         \-> LAW_CLARIFICATION_REQUEST <-/
                         \-> LAW_AMENDMENT_REQUEST <-/
                         \-> REWORK -> EXECUTIVE
                         \-> REJECTED
```

### 狀態規則

- `NEW`：任務尚未正式化。
- `LEGISLATIVE`：正在撰寫法律。
- `EXECUTIVE`：正在執行。
- `HARNESS_SUBMITTED`：證據已提交。
- `JUDICIARY`：正在驗證。
- `LAW_CLARIFICATION_REQUEST`：法律太模糊，需要澄清。
- `LAW_AMENDMENT_REQUEST`：法律本身需要修正。
- `REWORK`：審查未通過，需要修正。
- `PASSED`：已符合要求。
- `REJECTED`：踩到紅線。

### Harness 證據

每次狀態流轉都應留下證據：

- 規格文件
- 測試案例
- log
- 截圖
- 輸出檔
- 最終判決
