# AI Governance Framework for Multi-Agent Systems

A governed multi-agent system for teams that need clear acceptance criteria,
auditable execution, and reviewable verdicts.

多 Agent AI 治理框架，為需要清楚驗收、可稽核執行、可審查判決的團隊而設。

[![CI](https://github.com/bounce12340/agent-governance/actions/workflows/ci.yml/badge.svg)](https://github.com/bounce12340/agent-governance/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/bounce12340/agent-governance)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-bilingual-brightgreen)](README.md)

## Product overview / 產品概覽

### English

This repo turns AI collaboration into a governed workflow.
Instead of letting agents chat freely, it gives every task:

- a law
- an executor
- a judge
- a harness gate

That means you can define success first, build inside the rules, and review the result with evidence.

### 繁體中文

這個 repo 把 AI 協作變成一套有制度的流程。
不是讓 agent 自由聊天，而是讓每個任務都先具備：

- 法律
- 執行者
- 審查者
- harness 門檻

也就是先定義成功，再在規則內實作，最後用證據審查結果。

## What this is good for / 適合做什麼

- App planning / App 規劃
- Requirement validation / 需求驗證
- Code review governance / 程式碼審查治理
- Launch decision making / 上線決策
- Multi-agent accountability / 多 Agent 問責流程

## Quick tour / 快速導覽

- **Constitution**: global rules that every case must obey.
- **Legislative**: turns requests into laws and acceptance criteria.
- **Executive**: executes within the law.
- **Harness**: blocks judgment until evidence is ready.
- **Judiciary**: verifies the output and can request amendments.

- **憲法層**：所有案件都要遵守的全域規則。
- **立法權**：把需求轉成法律與驗收標準。
- **行政權**：只在法律內執行。
- **Harness**：證據沒準備好，就不能進司法審查。
- **司法權**：驗證輸出，必要時可以要求修法。

## Why it exists / 為什麼要做這個

Most multi-agent systems fail because they lack a stable contract.
Agents can talk, but nothing forces them to define success clearly.

This framework solves that by requiring every task to have:

- explicit acceptance criteria
- measurable outputs
- evidence bundles
- reviewable verdicts

多數多 Agent 系統的問題，是沒有穩定契約。
Agent 可以互相對話，但沒有人強迫它們先定義什麼叫成功。

這個框架的解法是：每個任務都必須具備：

- 明確的驗收標準
- 可量化的輸出
- 可追溯的證據包
- 可審查的判決結果

## Core principles / 核心原則

- **Testable before executable** / **先可驗證，再可執行**
- **No vague success criteria** / **禁止模糊成功定義**
- **Evidence over vibes** / **用證據，不用感覺**
- **Reviewable at every stage** / **每一階段都可審查**
- **Fail fast, fix fast** / **快速失敗，快速修正**

## System model / 系統模型

This version adds a constitution layer, feedback loops, role isolation,
and a hard harness gate.

這個版本加入了憲法層、反向回饋、角色隔離，以及強制的 harness gate。

```text
User / 使用者
  -> Constitution / 憲法層
  -> Legislative / 立法權
  -> Executive / 行政權
  -> Harness gate / 證據門檻
  -> Judiciary / 司法權
  -> Verdict / 最終判定
```

### Roles / 角色

#### Legislative / 立法權

Converts a request into law.
Defines:

- acceptance criteria
- metrics
- red lines
- evidence requirements

把需求轉成法律。
負責定義：

- 驗收標準
- 指標
- 紅線
- 證據需求

#### Executive / 行政權

Builds the deliverable inside the law.
Produces:

- implementation
- draft artifacts
- logs
- screenshots
- test output

在法律內完成交付物。
產出：

- 實作內容
- 草稿成果
- logs
- 截圖
- 測試輸出

#### Judiciary / 司法權

Checks the output against the law and constitution.
Can approve, reject, or request an amendment.
Returns:

- passed
- rework
- rejected

把輸出和法律逐條比對。
回傳：

- 通過
- 返工
- 拒絕

#### Harness Engineering / 驗證框架工程

Defines how proof is collected.
A claim is not complete unless it can be tested.
Judgment cannot happen until the harness gate is satisfied.

定義怎麼收集證據。
一個主張如果不能被驗證，就不算完成。

## Workflow / 工作流

1. **Write a law / 撰寫法律**
   - Define scope, metrics, red lines, and evidence.

2. **Execute / 執行**
   - Build only inside the law.

3. **Submit harness / 提交證據**
   - Package tests, evidence, and failure notes.

4. **Verify / 驗證**
   - Run the harness and issue a verdict.

5. **Rework if needed / 必要時返工**
   - If a red line is hit, the task goes back for revision.
   - Rework is capped to avoid infinite loops.

## Technical examples / 技術範例

These examples are written like technical specs, not marketing copy.

### 1. App idea validation / App 點子驗證

**Input**: Build a habit-tracking app for busy professionals.

#### App idea validation, legislative spec

- Target users: busy professionals, 25-45 years old.
- Success metric: at least 60% of test users say it solves a daily tracking problem.
- Red lines: no hidden tracking, no sensitive permissions without explanation.
- Feature scope: login, habit CRUD, daily check-in, history view.

#### App idea validation, executive output

- MVP build with a single core loop.
- Persistent storage for habits and check-ins.
- Basic onboarding and account handling.

#### App idea validation, judiciary checks

- Core flow works end to end.
- No crash during one full test session.
- Privacy policy exists and matches actual behavior.

#### App idea validation, harness artifacts

- Test checklist
- Screenshot set
- Crash log or clean run log
- Privacy policy link

### 2. Feature request review / 功能需求審查

**Input**: Add export-to-PDF for monthly reports.

#### Feature request review, legislative spec

- PDF must include title, date range, and summary tables.
- Max file size: 5 MB.
- Output must preserve UTF-8 text and mobile-friendly layout.
- No external payment or tracking behavior.

#### Feature request review, executive output

- Export function implemented in iOS and Android builds.
- PDF generated from the current report view.
- Error handling for empty data and permission failures.

#### Feature request review, judiciary checks

- Generated file opens correctly on both platforms.
- Text alignment and page breaks stay within spec.
- Empty-state behavior is documented and predictable.

#### Feature request review, harness artifacts

- Sample PDF files
- Render screenshots
- File size report
- Empty-state test case

### 3. API / code review workflow / API 與程式碼審查流程

**Input**: Review a FastAPI endpoint for auth and error handling.

#### API / code review workflow, legislative spec

- Authentication required for protected routes.
- Validation errors must return structured JSON.
- Logs must exclude secrets and personal data.
- Timeouts and failure states must be documented.

#### API / code review workflow, executive output

- Endpoint implementation.
- Unit tests and integration tests.
- Error mapping table.

#### API / code review workflow, judiciary checks

- Missing auth must fail.
- Invalid payload must return the right status code.
- Exceptions must not leak stack traces to users.

#### API / code review workflow, harness artifacts

- Test response snapshots
- Coverage report
- Logging sample
- Failure mode table

### 4. Launch decision / 上線決策

**Input**: Decide whether the app is ready for launch.

#### Launch decision, legislative spec

- Crash threshold: zero crashes in the critical path.
- Policy requirements: privacy policy, app metadata, permission disclosures.
- Release requirements: signed build, version number, release notes.

#### Launch decision, executive output

- Production build
- Screenshots
- Release notes
- Test report

#### Launch decision, judiciary checks

- All critical-path tests pass.
- No policy violations remain.
- Release package is complete.

#### Launch decision, harness artifacts

- Build artifact checksum
- Test matrix
- Store submission checklist
- Final go/no-go verdict

## Repo docs / 文件索引

### Core governance / 核心治理

- [Constitution / 憲法層](CONSTITUTION.md)
- [Governance architecture / 治理架構](docs/governance-architecture.md)
- [Governance config / 治理設定](config/governance.yaml)
- [Governance validator / 治理驗證腳本](scripts/validate_governance.py)

### Examples and references / 範例與參考

- [Governance cycle example / 治理流程範例](examples/governance_cycle.md)
- [APP law example / APP 法律範例](examples/app_law_example.md)
- [Harness test examples / Harness 測試例子](tests/harness_examples.md)
- [Data flow and state machine / 資料流與狀態機](docs/state-machine.md)
- [CLI and API reference / CLI 與 API 參考](docs/cli-api-reference.md)
- [Docs index / 文件索引](docs/README_INDEX.md)
- [Security policy / 安全性政策](SECURITY.md)
- [Code of conduct / 行為準則](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## What this is not / 這不是什麼

- Not free-form agent chat / 不是自由聊天型 Agent
- Not prompt chaos / 不是 prompt 大雜燴
- Not trust-me-bro AI / 不是「相信我就好」的 AI

## Status / 狀態

This repo is open-source friendly, bilingual, and easy to fork.

這個 repo 的目標是：開源友善、雙語清楚、方便 fork 與實驗。
