---
name: rl-advisor
description: Use when answering questions about the Kaiwu_2026 repository. Searches wiki/, memory, and git log to provide informed answers about code structure, experiments, competition stages, and RL design decisions.
version: 1.0.0
author: Qoobee
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, qa, knowledge, rl]
    related_skills: [repo-scanner, wiki-sync]
---

# RL Advisor

基于仓库知识库回答团队问题。

## When to Use

- 团队成员通过飞书提问仓库相关问题
- 需要跨赛段对比代码或方案
- 查找特定函数/配置的位置和用法
- 回顾实验历史和结论

Don't use for: 代码修改（用 git 工作流）、代码审查

## 回答策略

### 1. 优先检索 wiki/

先读取 `wiki/` 下的相关文件，这些是预构建的结构化索引：
- 架构问题 → `wiki/architecture.md`
- 函数位置 → `wiki/api-reference.md`
- 实验历史 → `wiki/experiments.md`
- 赛段知识 → `wiki/competition.md`

### 2. 补充检索

如果 wiki/ 中信息不足：
- 检查 Hermes memory 中的补充记录
- 执行 `git log --oneline -20` 查看最近变更
- 直接读取源文件确认细节

### 3. 回答格式

```
**回答**
{直接回答问题}

**依据**
- 来源文件：{path}
- 相关代码：{函数/类名}

**补充**
{如有相关的实验记录或历史变更，补充说明}
```

### 4. 赛段边界

回答时必须标明信息属于哪个赛段。如果问题涉及跨赛段对比，明确列出各赛段的差异。

### 5. 不确定时

如果无法从仓库知识中确定答案，明确告知：
- 已检索的范围
- 找到了什么
- 缺失什么
- 建议用户查看哪个文件

## 常见问题模式

| 问题类型 | 检索顺序 |
|---------|---------|
| "XX 函数在哪？" | wiki/api-reference.md → grep 源码 |
| "区域赛用了什么奖励？" | wiki/competition.md → 区域赛/conf/ |
| "最近改了什么？" | git log → wiki/index.md |
| "初赛和区域赛的网络有什么区别？" | wiki/architecture.md → 对比源码 |
| "实验 XX 的结论是什么？" | wiki/experiments.md → 实验记录 |
