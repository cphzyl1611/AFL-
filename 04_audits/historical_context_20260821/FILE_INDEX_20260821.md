# 文件索引

## 01_context
- CURRENT_STATE.md：2026-08-21 最新权威工程状态。
- NEW_CHAT_PROMPT.txt：新会话首条 Prompt，可直接复制。
- MISSING_REPO_FILES.md：当前包缺少的 WSL 仓库源码。
- WORKTREE_NOTES.md：工作树与历史临时 worktree 状态。

## 02_audits/v071
- v071_implementation_report.txt
- v071_independent_readonly_audit.txt

## 02_audits/gate2
- gate2_final_audit_and_hardening_log.txt
- changed_files.json
- machine-readable regression/scanner summaries（另见 03_machine_readable）

## 02_audits/levelc
- metadata_independent_audit.txt
- content_implementer_selftest.txt
- content_checkpoint_precommit_commit_log.txt
- content_independent_audit.txt

## 02_audits/scanner_history
- scanner_cross_version_contract_log.txt
说明：这是历史中间 scanner 与 FINAL 的交叉测试日志，不是当前权威实现。

## 03_machine_readable/gate2
- changed_files.json
- flowable_auth_validation_tests.txt
- full_unittest_summary.json
- git_baseline.json
- scanner_allowlist_tests.txt
- scanner_placeholder_tests.txt
- scanner_serialization_tests.txt
- secret_scan_summary.json
- summary.json

## 04_project_background
- AFL++源代码修改总纲.md
- 河南重大专项.docx
- 课题总体设计方案 docx
- 课题任务书 docx
- 西电-中期报告.docx

这些背景文档不是当前代码事实。当前代码事实必须以 53cb267 committed source + 最新独立审计为准。

## 05_user_action
- collect_repo_files.sh：在用户 WSL 上只读提取精确 checkpoint 源码并生成第二个 zip。
