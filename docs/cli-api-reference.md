# CLI and API Reference / CLI 與 API 參考

## English

This framework can be driven by CLI, scripts, or API calls.

### CLI commands

#### 1. Write a law

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

#### 2. Start execution

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP"
```

#### 3. Run verification

```bash
ai-gov judge run \
  --case CASE-001 \
  --harness tests/harness_examples.md
```

#### 4. Show verdict

```bash
ai-gov judge show CASE-001
```

### API shape

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

#### POST /judgments (English)

Verify a case.

Request fields:

- `case_id`
- `evidence`
- `result`

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

#### 1. 撰寫法律

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

#### 2. 啟動執行

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP"
```

#### 3. 執行驗證

```bash
ai-gov judge run \
  --case CASE-001 \
  --harness tests/harness_examples.md
```

#### 4. 顯示判決

```bash
ai-gov judge show CASE-001
```

### API 形式

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

#### POST /judgments (繁體中文)

驗證案件。

請求欄位：

- `case_id`
- `evidence`
- `result`

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
