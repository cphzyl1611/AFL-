你现在继续执行“河南重大专项 / AFL++ 自动化测试框架”项目。

第一轮不要修改代码，不要执行真实 Alfresco 请求，不要执行 fuzz。

请先阅读：
1. README_START_HERE.md
2. 01_context/CURRENT_STATE.md
3. 01_context/FILE_INDEX.md
4. 03_current_delta/MISSING_CURRENT_WORKTREE_FILES.md
5. 02_source/ 中两个 53cb267 source archive
6. 03_current_delta/ 当前文件及 patches
7. 04_audits/latest_reviews/
8. 04_audits/levelc/ 与 04_audits/gate2/
9. 06_background/AFL++源代码修改总纲.md

代码事实优先级：

CURRENT WORKING-TREE SOURCE
> exact committed source snapshot
> independent audit
> historical handoff/report

不要根据旧报告猜当前文件内容。

第一轮只做 READ-ONLY REVALIDATION：

A. 输出：
- pwd
- git branch --show-current
- git rev-parse HEAD
- git status --short
- 下列文件的 SHA256：
  - nv_http_harness.py
  - nv_http_body_adapter.py（若在 repo）
  - tests/test_nv_http_harness_representation_bridge.py（若在 repo）
  - scripts/run_alfresco_bounded_feedback.py
  - tests/test_alfresco_bounded_feedback.py

B. 独立确认 CB-1 representation bridge：
- body_only_mode=1 时 FULL HTTP 是否 byte-exact 提取 body
- plain body-only JSON 是否保持原路径
- malformed HTTP envelope 是否 fail-closed
- reject 是否不写 status / 不 mint exec_seq
- 运行 offline regression test 后再给验证等级

C. 独立确认 CB-2 bounded runner：
- build_run_layout 是否被 main 真正使用
- --preflight-only 是否有真实语义
- 是否执行 dedicated-node resolution
- 是否准备 fresh run-root
- 是否 render runtime target
- 是否具备 AFL launch
- 如果仍是 stub，只报告事实，不要先重构

D. 输出：
CB-1 =
CB-2 =

验证等级仅允许：
DESIGN CLAIM
IMPLEMENTED
VERIFIED BY IMPLEMENTER
INDEPENDENTLY VERIFIED
PARTIALLY VERIFIED
NOT VERIFIED

第一轮结束前：
- NO real Alfresco
- NO fuzz
- NO Flowable
- NO commit/push/merge/tag/reset/rebase
- 不输出任何 credential 值

最后给出“下一步最小动作”，不要越过当前 gate。
