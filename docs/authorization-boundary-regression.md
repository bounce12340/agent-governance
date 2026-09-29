# 授權邊界回歸案例與本機驗證（2026-09-29）

基準：`main` @ `1c996d2f564b804b3c98d934e31277f69f10606d`。本文件是基準版本的唯讀政策盤點；不變更產品政策、程式或測試。

| 合成案例 | 預期結果 | 既有回歸證據 |
| --- | --- | --- |
| Bearer 缺失／未知；匿名讀個案 | 401，不回傳 token | `tests/test_api.py::AuthenticationTest`、`test_an_anonymous_read_is_unauthorised` |
| BUILD 寫 law、REVIEW 交 harness、BUILD 作 judgment | 403，不能越角色寫入 | `tests/test_api.py::AuthorisationTest` |
| BUILD 寫權限外 artifact；EXECUTIVE 寫 verdict；合法與非法 key 混合 | 403／`IsolationError`；混合寫入整批拒絕 | `tests/test_api.py::test_an_artifact_outside_executive_authority_is_forbidden`、`tests/test_agency.py::WriteAuthorityTest` |
| JUDICIARY 獲禁讀、未列名或不准讀材料 | 明禁 key 拒絕，其他不准讀內容不進 prompt | `tests/test_runtime.py::RoleIsolationTest`、`tests/test_agency.py::MaterialsTest` |
| 多個角色共用 verdict 寫權或替終態指定角色 | 設定驗證拒絕 | `tests/test_agency.py::ConfigContractTest` |
| 三種已認證操作員讀同一個案 | 可讀稽核視圖、不能讀 evidence 原文；匿名 401 | `tests/test_api.py::test_any_authenticated_operator_may_read`、`test_the_view_never_returns_artifact_contents` |

**通過條件：**上述既有測試於所驗 SHA 執行通過，JSON/YAML 設定驗證通過。不 skip 或弱化 assert。**拒絕條件：**越角色可寫、混合 payload 部分寫入、禁讀資料進 prompt、讀取 evidence 原文或設定驗證失敗。

**待產品確認：**現行 `ai_gov/api.py:get_case` 允許任何已認證操作員讀取個案稽核視圖（包含 law、case_name 等，但不含 evidence 原文）。若要個案／角色隔離讀取或隱藏其他欄位，須先定義 owner、角色與欄位政策；現有授權不能推定新政策。

**基準版驗證：**`python3 -m unittest -q tests.test_agency tests.test_runtime tests.test_api tests.test_operators` → 123 tests OK（44.085s）；`python3 scripts/validate_governance.py config/governance.json` 與 `config/governance.yaml` 均 PASS。另兩次全套 `python3 -m unittest discover -s tests -p 'test_*.py' -q` 分別於 120s、240s 逾時，無完成摘要，不稱本輪 280 項通過；較早同 SHA 有 280 項通過紀錄但不代替本輪全套驗收。這份文件不改變測試／產品檔，新增文件 SHA 的遠端 CI 狀態須另核對，不能沿用基準版 CI。
