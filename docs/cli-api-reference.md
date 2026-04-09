# CLI and API Reference / CLI 與 API 參考

## English

This framework can be driven by CLI, scripts, or API calls.

### CLI commands

The commands below are the proposed governance surface for this framework.

#### 1. Write a law

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

#### 2. Request clarification

```bash
ai-gov law clarify \
  --case CASE-001 \
  --reason "The acceptance criteria are ambiguous"
```

#### 3. Start execution

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP"
```

#### 4. Submit harness

```bash
ai-gov harness submit \
  --case CASE-001 \
  --artifacts tests/harness_examples.md
```

#### 5. Run verification

```bash
ai-gov judge run \
  --case CASE-001 \
  --harness tests/harness_examples.md
```

#### 6. Request amendment

```bash
ai-gov judge amend \
  --case CASE-001 \
  --reason "The law needs a clearer crash threshold"
```

#### 7. Show verdict

```bash
ai-gov judge show CASE-001
```

### API shape

The API supports amendment and clarification requests so the flow is not strictly one-way.

#### POST /laws (English)

Create a law.

Request fields:

- `title`
- `acceptance_criteria`
- `red_lines`

#### POST /cases (English)

Create a case from a law.

Request fields:

- `law_id`
- `scope`
- `artifacts`

#### POST /harnesses (English)

Submit a harness bundle.

Request fields:

- `case_id`
- `test_plan`
- `evidence_bundle`
- `failure_mode_notes`

#### POST /judgments (English)

Verify a case.

Request fields:

- `case_id`
- `evidence`
- `result`

#### POST /law-amendments (English)

Request a law amendment.

Request fields:

- `case_id`
- `reason`
- `proposed_changes`

#### POST /law-clarifications (English)

Request law clarification.

Request fields:

- `case_id`
- `reason`
- `ambiguity_notes`

### Response model

```json
{
  "id": "LAW-001",
  "status": "passed",
  "summary": "All criteria satisfied"
}
```

### Recommended evidence

- survey data
- interview notes
- screenshots
- logs
- test output
- release build

## 繁體中文

這個框架可以用 CLI、腳本或 API 來驅動。

### CLI 指令

以下指令是這套治理框架的建議操作介面。

#### 1. 撰寫法律

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

#### 2. 提出澄清請求

```bash
ai-gov law clarify \
  --case CASE-001 \
  --reason "The acceptance criteria are ambiguous"
```

#### 3. 啟動執行

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP"
```

#### 4. 提交 harness

```bash
ai-gov harness submit \
  --case CASE-001 \
  --artifacts tests/harness_examples.md
```

#### 5. 執行驗證

```bash
ai-gov judge run \
  --case CASE-001 \
  --harness tests/harness_examples.md
```

#### 6. 提出修法請求

```bash
ai-gov judge amend \
  --case CASE-001 \
  --reason "The law needs a clearer crash threshold"
```

#### 7. 顯示判決

```bash
ai-gov judge show CASE-001
```

### API 形式

這個 API 會支援修法與澄清請求，讓流程不是單向線性。

#### POST /laws (繁體中文)

建立法律。

請求欄位：

- `title`
- `acceptance_criteria`
- `red_lines`

#### POST /cases (繁體中文)

根據法律建立案件。

請求欄位：

- `law_id`
- `scope`
- `artifacts`

#### POST /harnesses (繁體中文)

提交 harness 證據包。

請求欄位：

- `case_id`
- `test_plan`
- `evidence_bundle`
- `failure_mode_notes`

#### POST /judgments (繁體中文)

驗證案件。

請求欄位：

- `case_id`
- `evidence`
- `result`

#### POST /law-amendments (繁體中文)

提出法律修正請求。

請求欄位：

- `case_id`
- `reason`
- `proposed_changes`

#### POST /law-clarifications (繁體中文)

提出法律澄清請求。

請求欄位：

- `case_id`
- `reason`
- `ambiguity_notes`

### 回應模型

```json
{
  "id": "LAW-001",
  "status": "passed",
  "summary": "All criteria satisfied"
}
```

### 建議證據

- 問卷資料
- 訪談筆記
- 截圖
- logs
- 測試輸出
- release build
