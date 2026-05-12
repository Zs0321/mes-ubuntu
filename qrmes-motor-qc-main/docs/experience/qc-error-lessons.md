# QC Error Lessons

## 2026-03-10
- 现象: DB 直连读取受限（`Error: access permission denied`），本次走 `projects + picture` 降级链路。
- 高发约束: step_not_in_project_definition=35332, product_type_or_model_unresolved=12056, duplicate_capture_same_step=8633, project_unresolved=278.
- 修正策略: Prompt B 对工序名做归一化/弱模糊匹配，减少 strict exact match 带来的漏识别。
- 下次关注: 优先恢复 DB 读取权限，以补齐真实 detected/required 明细而非仅文件名推断。
