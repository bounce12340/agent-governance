# Model Interfaces / 模型接口

## English

### Plural by requirement, not by option

`role_isolation` has always declared `model: separate` for all three roles.
Until the runtime existed, that was a claim nobody checked. It is now enforced:
the validator rejects any config where two roles resolve to the same
`(interface, base_url, model)` triple.

The reason is the constitution's oldest rule — no role may judge its own
original reasoning. Three roles sharing one model are not isolated by having
different prompts. Their blind spots are correlated: what the legislative role
failed to consider, the judiciary running the same model will usually fail to
catch. Separate prompts split the instructions. Separate models split the
failure modes.

So the framework does not merely permit multiple model interfaces. It requires
them.

### Supported interfaces

| `interface` | Speaks to |
| --- | --- |
| `openai_chat_completions` | OpenAI, and any server copying its chat-completions shape |
| `anthropic_messages` | The Anthropic messages endpoint |
| `stub` | Nothing. Deterministic, offline, credential-free |

The first one is deliberately named after the wire format rather than the
vendor, because that format is what self-hosted and gateway servers implement.
Pointing `base_url` at a local endpoint needs no new adapter.

`stub` is what lets CI run the whole flow with no key and no network.

### Declaring a provider

```yaml
providers:
  openai_primary:
    interface: openai_chat_completions
    base_url: https://api.openai.com/v1
    model: gpt-4o
    model_env: OPENAI_MODEL
    api_key_env: OPENAI_API_KEY
    timeout_seconds: 60
    max_output_tokens: 4096
```

`model` is whatever identifier your account or server exposes; these move, so
treat the shipped values as examples and set your own.

`model_env` names an environment variable that overrides `model` at run time,
or `null` for a provider that declines overrides. A model id is a **default,
not a fact**: vendors rename and retire them, and a deployment that has to edit
a governance file to keep working will eventually edit it carelessly. The
validator applies the same rule as `api_key_env` — the value must look like a
variable name, so a model id written there is rejected.

The override is reported rather than hidden. `python3 -m runtime` prints
`model=gpt-5-turbo (OPENAI_MODEL)` when the environment won and
`model=gpt-4o (config)` when it did not, so the wiring readout always says
which model will actually be called. An empty variable counts as unset — a
shell exporting an empty string means "not configured", not "call the empty
model".

`api_key_env` names an **environment variable**. It is never the key itself —
the validator rejects any value that does not look like a variable name, since
a literal credential in a tracked config is a constitution violation.

Declaring a provider does not put it to work. `role_isolation.<role>.provider`
does that:

```yaml
role_isolation:
  judiciary:
    model: separate
    provider: openai_compatible_local
```

### Adding an interface

1. Subclass `ModelAdapter` in `runtime/adapters.py`, implementing
   `build_request` and `parse_response`, and register it in `INTERFACES`.
2. Add the same name to `KNOWN_INTERFACES` in `scripts/validate_governance.py`.
3. Add offline tests asserting the request shape and response parsing.

A test asserts that the two registries stay equal, so forgetting step 2 fails
CI rather than failing at runtime.

Request construction is separated from sending precisely so step 3 needs no
network and no credential.

### Checking the wiring (English)

```bash
python3 -m runtime                          # uses config/governance.yaml
python3 -m runtime config/governance.json
```

It prints which model interface sits in which seat and whether each credential
is present. It reports presence only, never the value, and it calls no model.
Exit code is `1` if any credential is missing.

### Dependency and secret rules

The runtime uses the standard library only. Vendor SDKs are not used, because
adding one would make `pip install` a precondition for running the governance
flow, and the validator's vendored YAML parser exists to avoid exactly that.

Credentials are read from the environment at call time. They are never logged,
never included in error messages, and never returned by `report()`. HTTP error
bodies are not surfaced either, since a response can echo request headers.

## 繁體中文

### 複數是要求，不是選項

`role_isolation` 一直都為三個角色宣告 `model: separate`。
在 runtime 出現之前，這只是一句沒有人檢查的主張。現在它被強制執行了：
只要有兩個角色解析到相同的 `(interface, base_url, model)` 三元組，驗證器就會拒絕。

理由來自憲法最早的一條規則 —— 任何角色都不能審自己的原始推理。
三個角色共用同一個模型，並不會因為 prompt 不同就達成隔離。
它們的盲點是高度相關的：立法角色沒想到的事，
用同一個模型的司法角色通常也抓不到。
分開 prompt 只是分開指令，分開模型才是分開失敗模式。

所以這個框架不只是「允許」接多個模型接口，而是「要求」如此。

### 支援的接口

| `interface` | 對接對象 |
| --- | --- |
| `openai_chat_completions` | OpenAI，以及任何沿用其 chat-completions 格式的伺服器 |
| `anthropic_messages` | Anthropic 的 messages 端點 |
| `stub` | 不對接任何東西。決定性、離線、不需金鑰 |

第一個刻意以傳輸格式命名，而不是以廠商命名，
因為自架伺服器與各種 gateway 實作的正是這個格式。
把 `base_url` 指向本機端點，不需要新增任何 adapter。

`stub` 讓 CI 可以在沒有金鑰、沒有網路的情況下跑完整個流程。

### 宣告一個 provider

```yaml
providers:
  openai_primary:
    interface: openai_chat_completions
    base_url: https://api.openai.com/v1
    model: gpt-4o
    model_env: OPENAI_MODEL
    api_key_env: OPENAI_API_KEY
    timeout_seconds: 60
    max_output_tokens: 4096
```

`model` 填你的帳號或伺服器實際提供的識別字串；
這些名稱會變動，請把 repo 內附的值當成範例，換成你自己的。

`model_env` 填一個環境變數名稱，執行時會覆蓋 `model`；
不接受覆蓋的 provider 就填 `null`。
模型 id 是**預設值，不是事實**：廠商會改名、會下架，
而一個必須改治理設定檔才能繼續運作的部署，遲早會有人隨手亂改。
驗證器對它套用跟 `api_key_env` 一樣的規則 ——
值必須看起來像變數名稱，所以把模型 id 寫在這裡會被拒絕。

覆蓋的結果會被報告出來，而不是悄悄生效。
環境變數贏的時候，`python3 -m runtime` 會印
`model=gpt-5-turbo (OPENAI_MODEL)`；沒贏的時候印 `model=gpt-4o (config)`，
所以接線報告永遠說得出實際會被呼叫的是哪個模型。
空字串等同於沒設定 —— shell 匯出一個空字串的意思是「沒設定」，
不是「呼叫一個叫做空字串的模型」。

`api_key_env` 填的是**環境變數名稱**，絕對不是金鑰本身 ——
驗證器會拒絕任何看起來不像變數名稱的值，
因為把金鑰寫進被版控的設定檔就是違反憲法。

宣告 provider 不等於啟用它，真正的綁定是
`role_isolation.<role>.provider`：

```yaml
role_isolation:
  judiciary:
    model: separate
    provider: openai_compatible_local
```

### 新增一個接口

1. 在 `runtime/adapters.py` 繼承 `ModelAdapter`，
   實作 `build_request` 與 `parse_response`，並註冊到 `INTERFACES`。
2. 在 `scripts/validate_governance.py` 的 `KNOWN_INTERFACES` 加入同一個名稱。
3. 加上離線測試，驗證請求格式與回應解析。

有一個測試會斷言這兩份註冊表必須相等，
所以忘記第 2 步會在 CI 就失敗，而不是等到執行時才炸。

請求的組裝與送出刻意分離，正是為了讓第 3 步不需要網路也不需要金鑰。

### 檢查接線狀況（繁體中文）

```bash
python3 -m runtime                          # 預設讀 config/governance.yaml
python3 -m runtime config/governance.json
```

它會印出哪個模型接口坐在哪個位子，以及各個金鑰是否存在。
它只回報「有沒有」，不會回報值，也不會呼叫任何模型。
只要有任何金鑰缺失，結束碼為 `1`。

### 相依與金鑰規則

runtime 只使用標準函式庫。不使用廠商 SDK，
因為那會讓 `pip install` 變成跑治理流程的前提條件，
而驗證器內建 YAML 解析器存在的理由，正是為了避免這件事。

金鑰在呼叫當下才從環境變數讀取。
它不會被記錄、不會出現在錯誤訊息、也不會出現在 `report()` 的輸出中。
HTTP 錯誤的回應內容同樣不會被揭露，因為回應有可能回音請求標頭。
