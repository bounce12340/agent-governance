# CLI and API Reference / CLI 與 API 參考

## English

Both surfaces below are implemented: the `ai-gov` CLI, and an HTTP API shipped
as a WSGI application. They write through the same role authority and the same
record store, so neither is a way around the other.

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
| `5` | the record changed underneath the write, which was refused |

### Writes are bound by role authority

Each command acts on behalf of one role and goes through that role's
`may_write` allowlist. `law clarify` writes as the executive; `judge amend` and
`judge run` write as the judiciary. An operator at a terminal is standing in
for a role and cannot do what that role could not — otherwise the CLI would be
a hole straight through role isolation.

### Concurrent writes are refused, not merged

Every case carries a `version`. A write asserts the version it was loaded with
is still the one on disk; if another writer got there first, the write is
refused with exit code `5` (HTTP `409`) and the caller reloads and retries.

Silently keeping the last write would erase whichever decision lost the race,
and the audit trail would not show that it happened. Two operators changing one
case at once is a governance event, so it is reported as one.

Records are written to a temporary file in the destination directory and then
renamed, so a reader never sees half a record and a crash mid-write leaves the
previous one intact.

### The HTTP API

`ai_gov/api.py` exports `create_app()`, which returns a WSGI application. There
is no bundled server: WSGI is already in the standard library, so a deployment
uses the server it already runs.

```bash
gunicorn 'ai_gov.api:create_app()'      # or uWSGI, waitress, mod_wsgi
python3 -m ai_gov.api                   # development only, see below
```

`python3 -m ai_gov.api` serves on `wsgiref.simple_server`, which is
single-threaded and has no TLS. **Do not run it in production** — every
operator token would cross the wire in clear text. It exists so the endpoints
can be exercised locally without installing anything.

#### Operators (English)

The CLI can treat filesystem access as its authorisation: whoever can run the
binary can already read the store. HTTP has no such boundary, so every request
names an operator with a bearer token:

```yaml
operators:
  reviewer:
    token_env: AI_GOV_TOKEN_REVIEWER
    may_act_as: [judiciary]
```

`token_env` names an environment variable, never a token — the same rule
providers follow for keys. An operator may only act as the roles it lists, so
the HTTP surface can never be wider than role isolation allows. Two operators
may not share one variable: indistinguishable operators defeat the point of
naming them separately.

```http
Authorization: Bearer $AI_GOV_TOKEN_REVIEWER
```

Every configured operator is compared in constant time, and an operator whose
variable is unset can never match — an absent credential must not authenticate
as an absent token. A refusal never says which token was close.

#### POST /laws (English)

Create a law. Acts as **legislative**.

```json
{"title": "App Launch Law",
 "acceptance_criteria": ["30 survey responses", "5 interviews"],
 "red_lines": ["no missing privacy policy"]}
```

#### POST /cases (English)

Open a case under a law. Acts as **legislative**.

```json
{"law_id": "LAW-001", "name": "Habit App MVP", "request": "Build a habit tracker"}
```

`request` is intake, not a role's write: `NEW` declares no acting role, so the
original request has no author inside the system. It defaults to `name`.

#### POST /harnesses (English)

Submit evidence. Acts as **executive**.

```json
{"case_id": "CASE-001",
 "artifacts": {"test_plan": "30 responses, 5 interviews",
               "evidence_bundle": "survey export, 31 rows"}}
```

The response reports which required artifacts are still missing and which
present ones fail their mechanical checks, with the config's verdict for each.
Hollow evidence is recorded rather than refused — an artifact that says nothing
is still something the executive submitted. An artifact outside executive
authority is `403`.

#### POST /judgments (English)

Verify a case. Acts as **judiciary**.

```json
{"case_id": "CASE-001", "unresolved_law_items": 0}
```

**There is no `result` field, and sending one is `422`.** A judgment is a
request, not an assertion: the client submits the facts a verdict is derived
from, the server runs the executor, and the response reports where the graph
ended up. A caller able to post `result: "PASSED"` would make every guard, loop
bound and evidence requirement in this repo decorative.

A verdict source is required, exactly as on the CLI: either `with_models: true`
or at least one of `unresolved_law_items`, `defective_law_items`,
`red_line_violated`. With neither, the case would route to `PASSED` on default
values.

A `REJECTED` verdict is a successful request. The verdict is in the body;
using an HTTP error for it would conflate "the system refused to answer" with
"the system answered no".

#### POST /law-amendments (English)

Request a law amendment. Acts as **judiciary**.

```json
{"case_id": "CASE-001", "reason": "The law needs a crash threshold",
 "proposed_changes": ["state a crash rate"]}
```

`proposed_changes` is folded into the `amendment_reason` artifact rather than
written as its own key: the judiciary's `may_write` has no such key, and the
HTTP layer must not widen a role's authority by inventing one.

#### POST /law-clarifications (English)

Request law clarification. Acts as **executive**.

```json
{"case_id": "CASE-001", "reason": "The acceptance criteria are ambiguous"}
```

#### GET /cases/{id} (English)

The audit view: state, route taken, harness coverage, loop usage against each
bound, repair counts, checkpoint counts and recorded verdict facts. Any
authenticated operator may read it.

It returns **no artifact contents**. Handing back evidence text would need a
role-scoped read, and this layer knows which operator is asking, not which role.

### Response model

Every response carries the same three keys, plus per-endpoint detail:

```json
{
  "id": "CASE-001",
  "status": "PASSED",
  "summary": "case ended at PASSED"
}
```

Errors use the same shape with `"status": "error"` and the reason in `summary`.

| Code | Meaning |
| --- | --- |
| `200` / `201` | the request succeeded; a verdict, if any, is in the body |
| `400` | the body is not valid JSON |
| `401` | no bearer token, or no operator matched it |
| `403` | the operator may not act as that role, or the role may not write that key |
| `404` | no such law, case, or endpoint |
| `405` | wrong method; the `Allow` header says which are accepted |
| `409` | the record changed underneath the write, which was refused |
| `413` | the body is over 1 MiB |
| `422` | the body is well-formed JSON but not a usable request |

### Recommended evidence

- survey data
- interview notes
- screenshots
- logs
- test output
- release build

## 繁體中文

底下兩個介面都已經實作：`ai-gov` CLI，以及以 WSGI 應用形式出貨的 HTTP API。
兩者透過同一套角色權限、寫進同一份紀錄庫，
所以誰都不是繞過對方的後門。

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
| `5` | 紀錄在這次寫入之前被別人改過，寫入遭拒 |

### 寫入受角色權限約束

每個指令都代表某一個角色行動，並且會通過該角色的 `may_write` 允許清單。
`law clarify` 以行政權寫入，`judge amend` 與 `judge run` 以司法權寫入。
終端機前的操作者是代替某個角色行動，
不能做到那個角色做不到的事 ——
否則這個 CLI 就是直接貫穿角色隔離的一個洞。

### 併發寫入會被拒絕，不會被合併

每個案件都帶著一個 `version`。
寫入時會主張「讀進來的版本仍然是磁碟上的版本」；
如果有別的寫入者先到，這次寫入就會被拒絕，
結束碼 `5`（HTTP `409`），呼叫方重新載入後再試。

安靜地保留最後一次寫入，等於抹掉在競爭中落敗的那個決定，
而稽核軌跡上完全看不出這件事發生過。
兩個操作者同時改同一個案件是一個治理事件，所以它會被當成事件回報。

紀錄會先寫到目標目錄下的暫存檔再改名，
因此讀取者永遠不會看到半份紀錄，寫到一半當掉也不會毀掉前一份。

### HTTP API

`ai_gov/api.py` 匯出 `create_app()`，回傳一個 WSGI 應用。
這裡不附伺服器：WSGI 本來就在標準函式庫裡，
部署的人用自己已經在跑的伺服器就好。

```bash
gunicorn 'ai_gov.api:create_app()'      # 或 uWSGI、waitress、mod_wsgi
python3 -m ai_gov.api                   # 只能用於開發，見下
```

`python3 -m ai_gov.api` 跑的是 `wsgiref.simple_server`，
單執行緒、沒有 TLS。**不可以用在正式環境** ——
所有操作者 token 都會以明文通過網路。
它存在的目的只是讓人不必安裝任何東西就能在本機試這些端點。

#### 操作者（繁體中文）

CLI 可以把檔案系統存取當成授權：能跑這支程式的人本來就讀得到紀錄庫。
HTTP 沒有這道邊界，所以每個請求都要用 bearer token 表明自己是哪個操作者：

```yaml
operators:
  reviewer:
    token_env: AI_GOV_TOKEN_REVIEWER
    may_act_as: [judiciary]
```

`token_env` 填的是環境變數名稱，絕不是 token 本身 ——
跟 provider 放金鑰的規則完全一樣。
操作者只能代理它列出的角色，
所以 HTTP 介面永遠不可能比角色隔離允許的範圍更寬。
兩個操作者不能共用同一個變數：
分辨不出來的操作者，等於白白替它們取了不同名字。

```http
Authorization: Bearer $AI_GOV_TOKEN_REVIEWER
```

每個設定過的操作者都會被比對，而且是常數時間比對；
變數沒設定的操作者永遠比不中 ——
沒有憑證不能當成「以缺席的 token 通過驗證」。
被拒絕時也不會透露哪一個 token 比較接近。

#### POST /laws (繁體中文)

建立法律。以**立法權**行動。

```json
{"title": "App Launch Law",
 "acceptance_criteria": ["30 survey responses", "5 interviews"],
 "red_lines": ["no missing privacy policy"]}
```

#### POST /cases (繁體中文)

在某條法律底下開案。以**立法權**行動。

```json
{"law_id": "LAW-001", "name": "Habit App MVP", "request": "Build a habit tracker"}
```

`request` 屬於 intake，不是任何角色的寫入：
`NEW` 沒有宣告行動角色，所以原始請求在系統內部沒有作者。
沒填的話預設用 `name`。

#### POST /harnesses (繁體中文)

提交證據。以**行政權**行動。

```json
{"case_id": "CASE-001",
 "artifacts": {"test_plan": "30 responses, 5 interviews",
               "evidence_bundle": "survey export, 31 rows"}}
```

回應會列出還缺哪些必要證據、哪些已交的證據沒通過機械檢查，
以及設定檔對這兩種情況各自的判定。
空洞的證據會被記錄而不是被拒絕 ——
一份什麼都沒說的證據，仍然是行政權交出來的東西。
超出行政權權限的 artifact 則回 `403`。

#### POST /judgments (繁體中文)

驗證案件。以**司法權**行動。

```json
{"case_id": "CASE-001", "unresolved_law_items": 0}
```

**沒有 `result` 欄位，送了就是 `422`。**
判決是**請求**，不是**斷言**：
客戶端送出判決所依據的事實，由伺服器執行狀態機，
回應只是報告圖最後停在哪裡。
如果呼叫方可以直接送 `result: "PASSED"`，
這個 repo 裡所有的 guard、迴圈上限與證據要求就全都變成裝飾品。

跟 CLI 一樣，必須提供判決來源：`with_models: true`，
或 `unresolved_law_items`、`defective_law_items`、`red_line_violated` 至少其一。
兩者皆無時，案件會靠預設值一路走到 `PASSED`。

`REJECTED` 是一次**成功**的請求。
判決在回應主體裡；用 HTTP 錯誤來表達它，
等於把「系統拒絕回答」跟「系統回答不通過」混為一談。

#### POST /law-amendments (繁體中文)

提出法律修正請求。以**司法權**行動。

```json
{"case_id": "CASE-001", "reason": "The law needs a crash threshold",
 "proposed_changes": ["state a crash rate"]}
```

`proposed_changes` 會併進 `amendment_reason` 這份 artifact，
而不是自成一個 key：司法權的 `may_write` 裡沒有這個 key，
HTTP 這一層不可以靠發明一個新 key 來擴張角色權限。

#### POST /law-clarifications (繁體中文)

提出法律澄清請求。以**行政權**行動。

```json
{"case_id": "CASE-001", "reason": "The acceptance criteria are ambiguous"}
```

#### GET /cases/{id} (繁體中文)

稽核視圖：狀態、走過的路線、harness 覆蓋率、
各迴圈的使用次數對上限、修復次數、checkpoint 次數，以及已記錄的判決事實。
任何通過驗證的操作者都可以讀。

它**不回傳任何 artifact 的內容**。
交出證據原文需要一次以角色為範圍的讀取，
而這一層只知道是哪個操作者在問，不知道是哪個角色在問。

### 回應模型

每個回應都帶同樣三個 key，再加上各端點自己的細節：

```json
{
  "id": "CASE-001",
  "status": "PASSED",
  "summary": "case ended at PASSED"
}
```

錯誤用同樣的形狀，`"status": "error"`，原因放在 `summary`。

| 狀態碼 | 意義 |
| --- | --- |
| `200` / `201` | 請求成功；若有判決，判決在回應主體裡 |
| `400` | 主體不是合法的 JSON |
| `401` | 沒有 bearer token，或沒有操作者比中 |
| `403` | 操作者不能代理該角色，或該角色不能寫這個 key |
| `404` | 查無此法律、案件或端點 |
| `405` | 方法錯誤；`Allow` 標頭會說明接受哪些方法 |
| `409` | 紀錄在這次寫入之前被別人改過，寫入遭拒 |
| `413` | 主體超過 1 MiB |
| `422` | 主體是合法 JSON，但不是一個可用的請求 |

### 建議證據

- 問卷資料
- 訪談筆記
- 截圖
- logs
- 測試輸出
- release build
