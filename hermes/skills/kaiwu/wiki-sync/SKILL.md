---
name: wiki-sync
description: Use after a git commit to incrementally update wiki/ based on the diff. Triggered by post-commit hook automatically. Updates affected wiki files and Hermes memory.
version: 1.0.0
author: Qoobee
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, wiki, git-hook, incremental]
    related_skills: [repo-scanner, rl-advisor]
---

# Wiki Sync

git commit 后增量更新 wiki/ 索引。

## When to Use

- 由 post-commit hook 自动触发
- 手动调用：`/wiki-sync commit="msg" diff="stat"`

Don't use for: 首次建索引（用 repo-scanner）、代码审查

## 执行流程

### Step 1: 解析输入

从参数中提取：
- `commit` — 提交信息
- `diff` — `git diff --stat` 输出

如果参数为空，自行执行：
```bash
git diff --stat HEAD~1 HEAD
git log -1 --pretty=%B
```

### Step 2: 判断变更范围

根据 diff 中的文件路径判断需要更新哪些 wiki 文件：

| 变更路径 | 更新的 wiki 文件 |
|---------|-----------------|
| `*/conf/*.py` | `api-reference.md`、`competition.md` |
| `*/feature/*.py` | `api-reference.md`、`architecture.md` |
| `*/model/*.py` | `api-reference.md`、`architecture.md` |
| `*/algorithm/*.py` | `api-reference.md`、`architecture.md` |
| `*/workflow/*.py` | `architecture.md` |
| `*/agent.py` | `architecture.md`、`index.md` |
| `docs/*.md` | `competition.md`、`index.md` |
| `实验记录/*` | `experiments.md` |
| `参考资料/*` | `competition.md` |

如果变更涉及 3 个以上 wiki 文件，建议改用 `/repo-scanner` 全量重建。

### Step 3: 增量更新

对受影响的 wiki 文件：
1. 读取当前内容
2. 根据 diff 中的变更，更新对应章节
3. 更新"最近更新"区域，添加 commit 信息
4. 写回文件

### Step 4: 更新 Memory

如果 commit 包含以下内容，写入 Hermes memory：
- 新增的函数或类 → 记录名称和位置
- 配置参数变更 → 记录参数名和新值
- 实验结论 → 记录实验名和结论

### Step 5: 通知（可选）

如果 commit 信息包含 `feat:`、`refactor:`、`BREAKING` 等标记，通过飞书通知团队：
```
仓库更新：{commit_message}
变更文件：{file_count} 个
wiki 已自动同步
```

## 验证清单

- [ ] 受影响的 wiki 文件已更新
- [ ] "最近更新"区域包含新 commit
- [ ] memory 已同步（如有新函数/配置）
