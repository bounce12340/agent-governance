# CLI and API Reference / CLI 與 API 參考

## English

The CLI below is implemented. The HTTP API further down is not — it is still a
proposed shape.

### Running it

No install step and no dependencies:

```bash
./bin/ai-gov --help          # from a checkout
python3 -m ai_gov --help     # equivalent
```

Records live in `.ai-gov/` by default. Override with `--store DIR` or the
`AI_GOV_STORE` environment variable. Laws and cases are plain JSON files, one
per record, because a governance record that needs a database to be read back
is a governance record nobody will audit.

### CLI commands

#### 1. Write a law

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

Prints the allocated `LAW-001`. A law with no `--metric` is accepted but says
so: nothing about it can be verified.

#### 2. Start a case

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP" \
  --request "Build a habit tracking app"
```

#### 3. Submit harness evidence

```bash
ai-gov harness submit \
  --case CASE-001 \
  --artifact evidence_bundle=reports/run.md \
  --note test_plan="30 responses, 5 interviews"
```

`--artifact NAME=PATH` attaches a file's contents; `--note NAME=TEXT` attaches
inline text. Both are repeatable. The command reports which required artifacts
are still missing.

#### 4. Report and supervise progress

```bash
ai-gov case checkpoint --case CASE-001 \
  --completed "auth flow done" --blocked "none" \
  --next-step "storage layer" --eta "2 days"

ai-gov case supervise --case CASE-001 [--escalate]
```

Every field is required — a report missing `blocked` or `eta` is refused. See
[Long-task supervision](long-task-supervision.md).

#### 5. Request clarification

```bash
ai-gov law clarify \
  --case CASE-001 \
  --reason "The acceptance criteria are ambiguous"
```

#### 6. Run verification

```bash
ai-gov judge run --case CASE-001 --unresolved 0
ai-gov judge run --case CASE-001 --red-line
ai-gov judge run --case CASE-001 --with-models
```

**A verdict source is required.** Without `--with-models` or one of
`--unresolved` / `--defective` / `--red-line`, the command refuses to run.
Running with neither would let the case route to `PASSED` on default values —
a success claimed without evidence, which the constitution forbids.

`--with-models` lets the bound judiciary model decide. The other flags record a
human verdict. Both are written with judiciary authority and no more.

#### 7. Request amendment

```bash
ai-gov judge amend \
  --case CASE-001 \
  --reason "The law needs a clearer crash threshold"
```

#### 8. Show verdict

```bash
ai-gov judge show CASE-001
ai-gov case list
```

`show` prints the state, the route taken, harness coverage per artifact, loop
usage against each bound, and the recorded verdict facts.

### Exit codes

The verdict is in the exit code, so a pipeline can branch on it without parsing
prose.

| Code | Meaning |
| --- | --- |
| `0` | command succeeded; for `judge run`, the case reached `PASSED` |
| `1` | usage error, unknown record, or a refused write |
| `2` | the case is blocked — incomplete harness evidence, or an overdue checkpoint |
| `3` | the case reached `REJECTED` |
| `4` | a loop stagnated and escalated, or checkpoints passed the miss ceiling |

### Writes are bound by role authority

Each command acts on behalf of one role and goes through that role's
`may_write` allowlist. `law clarify` writes as the executive; `judge amend` and
`judge run` write as the judiciary. An operator at a terminal is standing in
for a role and cannot do what that role could not — otherwise the CLI would be
a hole straight through role isolation.

### API shape (proposed)

The HTTP surface below is **not implemented**. It is recorded here as the
intended shape, and supports amendment and clarification requests so the flow
is not strictly one-way.

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

以下的 CLI 已經實作完成。再下面的 HTTP API 尚未實作，只是預定的形式。

### 如何執行

不需要安裝，也沒有任何相依：

```bash
./bin/ai-gov --help          # 直接從 checkout 執行
python3 -m ai_gov --help     # 等效寫法
```

紀錄預設存在 `.ai-gov/`，可用 `--store DIR` 或環境變數 `AI_GOV_STORE` 覆蓋。
法律與案件都是一筆一個 JSON 檔，
因為需要資料庫才讀得回來的治理紀錄，就是不會有人去稽核的治理紀錄。

### CLI 指令

#### 1. 撰寫法律

```bash
ai-gov law create \
  --title "App Launch Law" \
  --metric "30 survey responses" \
  --metric "5 interviews" \
  --redline "no missing privacy policy"
```

會印出配發的 `LAW-001`。
沒有任何 `--metric` 的法律仍會被接受，但會明講：它沒有任何東西可以被驗證。

#### 2. 啟動案件

```bash
ai-gov case start \
  --law LAW-001 \
  --name "Habit App MVP" \
  --request "Build a habit tracking app"
```

#### 3. 提交 harness 證據

```bash
ai-gov harness submit \
  --case CASE-001 \
  --artifact evidence_bundle=reports/run.md \
  --note test_plan="30 responses, 5 interviews"
```

`--artifact NAME=PATH` 附上檔案內容，`--note NAME=TEXT` 附上行內文字，
兩者都可重複使用。指令會回報還缺哪些必要證據。

#### 4. 回報與監督進度

```bash
ai-gov case checkpoint --case CASE-001 \
  --completed "auth flow done" --blocked "none" \
  --next-step "storage layer" --eta "2 days"

ai-gov case supervise --case CASE-001 [--escalate]
```

每個欄位都是必填 —— 少了 `blocked` 或 `eta` 的回報會被拒絕。
詳見[長任務監督](long-task-supervision.md)。

#### 5. 提出澄清請求

```bash
ai-gov law clarify \
  --case CASE-001 \
  --reason "The acceptance criteria are ambiguous"
```

#### 6. 執行驗證

```bash
ai-gov judge run --case CASE-001 --unresolved 0
ai-gov judge run --case CASE-001 --red-line
ai-gov judge run --case CASE-001 --with-models
```

**必須提供判決來源。**
沒有 `--with-models`，也沒有 `--unresolved` / `--defective` / `--red-line` 其中之一時，
指令會拒絕執行。
兩者皆無而硬跑，案件會靠預設值一路走到 `PASSED` ——
那就是沒有證據卻宣稱成功，而憲法禁止這件事。

`--with-models` 讓綁定的司法權模型下判斷，其他旗標則記錄人工判決。
兩者都以司法權的權限寫入，不會更多。

#### 7. 提出修法請求

```bash
ai-gov judge amend \
  --case CASE-001 \
  --reason "The law needs a clearer crash threshold"
```

#### 8. 顯示判決

```bash
ai-gov judge show CASE-001
ai-gov case list
```

`show` 會印出狀態、走過的路線、逐項的 harness 覆蓋率、
各迴圈的使用次數對上限，以及已記錄的判決事實。

### 結束碼

判決結果就在結束碼裡，讓流程可以直接分支，不必去解析文字。

| 結束碼 | 意義 |
| --- | --- |
| `0` | 指令成功；對 `judge run` 而言代表案件走到 `PASSED` |
| `1` | 用法錯誤、查無紀錄，或寫入被拒絕 |
| `2` | 案件被擋住 —— harness 證據不完整，或 checkpoint 逾期 |
| `3` | 案件走到 `REJECTED` |
| `4` | 某個迴圈停滯並升級，或 checkpoint 漏報超過上限 |

### 寫入受角色權限約束

每個指令都代表某一個角色行動，並且會通過該角色的 `may_write` 允許清單。
`law clarify` 以行政權寫入，`judge amend` 與 `judge run` 以司法權寫入。
終端機前的操作者是代替某個角色行動，
不能做到那個角色做不到的事 ——
否則這個 CLI 就是直接貫穿角色隔離的一個洞。

### API 形式（提案中）

以下的 HTTP 介面**尚未實作**，這裡記錄的是預定形式。
它會支援修法與澄清請求，讓流程不是單向線性。

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
