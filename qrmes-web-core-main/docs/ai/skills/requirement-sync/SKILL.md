---
name: requirement-sync
description: 在需求分析、实现前后、打包交付前回看并同步 REQUIREMENTS 的任务型 skill。适用于需求模糊、出现长期规则变化、实现与文档可能漂移、需要判断是否必须更新 requirement 的场景。
---

# Requirement Sync

这个 skill 用于防止实现、口头讨论和 requirement 文档逐渐漂移。

## 何时使用

当满足以下任一条件时使用：

- 开始分析一个新需求
- 对实现路径存在犹豫
- 发现口头描述和现有代码不一致
- 发现 requirement 未覆盖当前行为
- 本次改动引入新的长期规则
- 打包、提交、交付前做最终核对

## 固定动作

1. 先回看 requirement 中的相关章节
2. 判断当前需求是否与 requirement 一致
3. 判断 requirement 是否缺少本次实现依赖的关键信息
4. 如果本次变更会改变长期有效行为，计划同步回写

## 输出模板

```md
## Requirement Review

已回看的 requirement 章节：
- 

与当前需求一致的部分：
- 

存在缺口或冲突的部分：
- 

本次是否需要更新 requirement：
- 是 / 否

如果需要更新，计划补充：
- 
```

## 必须停手确认的情况

- requirement 与工程师口头要求冲突
- requirement 没有记录当前稳定行为，但该行为会影响实现选择
- 本次改动会新增长期规则，但工程师尚未确认是否纳入 requirement

## 交付前检查

交付前至少确认：

- 实现是否符合 requirement
- requirement 是否需要同步更新
- 新行为和旧行为是否都已验证
- fallback/default 是否在文档和实现中都可见
