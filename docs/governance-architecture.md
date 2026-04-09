# Governance Architecture / 治理架構

## English

This repo is organized around five core ideas:

1. **Constitution layer**
   - Global constraints that apply to every task.
   - Prevents local laws from violating platform-wide rules.

2. **Legislative layer**
   - Turns requests into laws.
   - Produces acceptance criteria, red lines, and metrics.

3. **Executive layer**
   - Executes only inside the law.
   - Produces deliverables and evidence.

4. **Harness layer**
   - Defines how proof is collected.
   - Blocks judgment if the evidence bundle is incomplete.

5. **Judiciary layer**
   - Verifies the result against the law and constitution.
   - Can approve, reject, or request amendments.

### Feedback paths

- **Judiciary -> Legislative**: law amendment request
- **Executive -> Legislative**: clarification request
- **Harness -> Judiciary**: incomplete or invalid evidence

### Rework control

To avoid infinite loops, rework is capped.
After a fixed number of failed cycles, the case is rejected.

### Role isolation

Each role must be isolated.
That means separate prompts, separate authority, and separate access to internal reasoning.
A role should not be able to audit its own original decision.

## 繁體中文

這個 repo 由五個核心概念組成：

1. **憲法層**
   - 套用在所有任務上的全域限制。
   - 避免下位法律違反平台底線。

2. **立法層**
   - 把需求轉成法律。
   - 產出驗收標準、紅線與指標。

3. **行政層**
   - 只能在法律內執行。
   - 產出交付物與證據。

4. **Harness 層**
   - 定義怎麼收集證據。
   - 若證據包不完整，就不能進司法審查。

5. **司法層**
   - 把結果和法律、憲法逐條比對。
   - 可以通過、拒絕，或要求修法。

### 回饋路徑

- **司法 -> 立法**：法律修正請求
- **行政 -> 立法**：法律澄清請求
- **Harness -> 司法**：證據不完整或無效

### Rework 控制

為了避免無限迴圈，rework 必須設上限。
超過固定次數後，案件會被直接拒絕。

### 角色隔離

每個角色都必須隔離。
意思是要有不同的 prompt、不同的權限、不同的內部資訊存取。
任何角色都不能審自己的原始決策。
