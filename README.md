# Separation of Powers for AI Agents
# AI 三權分立治理框架

A governance framework for AI agents built on **Legislative, Executive, Judiciary**, plus **Harness Engineering**.

一套把 AI Agent 協作從「自由聊天」升級成「制度化治理」的框架，結合 **立法權、行政權、司法權**，並加入 **Harness Engineering** 的驗收精神。

## Why this exists / 為什麼要做這個

### English
Most multi-agent systems fail for the same reason, they let agents talk too freely without a stable contract.
This project fixes that by making every task pass through:
1. **Legislative**, defines the law and acceptance criteria.
2. **Executive**, executes within the law.
3. **Judiciary**, verifies results and rejects non-compliance.
4. **Harness Engineering**, makes verification explicit, repeatable, and testable.

### 繁體中文
多數多 Agent 系統失敗的原因很像，Agent 可以自由聊天，但沒有穩定契約。
這個專案的解法是把每個任務都放進制度裡：
1. **立法權**，先定義法律與驗收標準。
2. **行政權**，在法律框架內執行。
3. **司法權**，負責審查結果並退回不合格產出。
4. **Harness Engineering**，讓驗證變成可重複、可測試、可追蹤的流程。

## Core principles / 核心原則

- **Testable before executable** / **先可驗證，再可執行**
- **No vague success criteria** / **禁止模糊成功定義**
- **Judgment over guesswork** / **用審查取代猜測**
- **Audit every result** / **每個結果都要可追溯**
- **Fail fast, fix fast** / **快速失敗，快速修正**

## Architecture / 架構

```text
User / 使用者
  -> Legislative / 立法權
  -> Executive / 行政權
  -> Judiciary / 司法權
  -> Final verdict / 最終判定
```

### Roles

- **Legislative**: converts a request into laws, acceptance criteria, and red lines.
- **Executive**: produces the actual deliverable.
- **Judiciary**: checks the deliverable against the law.
- **Harness layer**: defines the tests, fixtures, logs, and evidence needed for verification.

- **立法權**：把需求轉成法律、驗收標準與紅線。
- **行政權**：負責做出真正的產出。
- **司法權**：把產出和法律逐條比對。
- **Harness 層**：定義測試、樣本、日誌與證據，讓驗證可落地。

## Quick start / 快速開始

### 1. Write a law / 撰寫法律
Describe the target, constraints, metrics, and red lines.

### 2. Execute / 執行
Build the product within those constraints.

### 3. Verify / 驗證
Run the harness and judge pass/fail.

## Example use cases / 使用情境

- App idea validation / App 概念驗證
- Multi-agent project planning / 多 Agent 專案規劃
- Product requirement specification / 產品需求規格
- Code review governance / 程式碼審查治理

## Example tests / 測試例子

See:
- [examples/app_law_example.md](examples/app_law_example.md)
- [tests/harness_examples.md](tests/harness_examples.md)

## Status / 狀態

This repo is designed to be open-source friendly, bilingual, and easy to fork.

這個 repo 的目標是：開源友善、雙語清楚、方便 fork 與實驗。
