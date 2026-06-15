---
name: repo-sync
description: 从 GitHub 拉取最新代码，处理 stash/冲突，同步后通知飞书群聊并触发 wiki 更新。
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [kaiwu, git, sync, cron]
    related_skills: [wiki-sync, repo-scanner]
---

# Repo Sync

每日从 GitHub 拉取 Kaiwu_2026 最新代码并同步。

## When to Use

- 定时任务自动触发（每天 09:00）
- 手动调用：`/repo-sync`

Don't use for: 首次建索引（用 repo-scanner）、日常小改动提交（直接 git add/commit/push）

## 执行流程

### Step 1: Fetch

```bash
cd /root/Kaiwu_2026 && git fetch origin 2>&1
```

如果 fetch 失败（网络问题），输出错误并通知飞书后结束。

### Step 2: 检查本地未提交改动

```bash
git status --porcelain
```

- 有输出（有改动）→ `git stash push -m "repo-sync: auto stash $(date +%Y%m%d-%H%M)"` 暂存
- 无输出（干净）→ 继续

### Step 3: 检查差异并拉取

```bash
AHEAD=$(git rev-list --count origin/dev..HEAD)
BEHIND=$(git rev-list --count HEAD..origin/dev)
```

| 情况 | 处理 |
|------|------|
| BEHIND=0, AHEAD=0 | 已是最新，输出摘要，跳到 Step 6 |
| BEHIND>0, AHEAD=0 | `git pull --rebase origin dev` |
| BEHIND=0, AHEAD>0 | 本地有未推送 commit，输出提示，不 push |
| BEHIND>0, AHEAD>0 | 分叉，输出警告，通知飞书，不自动处理 |

### Step 4: 恢复 stash

如果 Step 2 做了 stash：

```bash
git stash pop 2>&1
```

- 成功 → 继续
- 有冲突 → 输出冲突文件列表，**保留 stash 不丢**，通知飞书

### Step 5: 触发 wiki 更新

如果 Step 3 拉取到了新 commit（BEHIND>0）：

```bash
DIFF_STAT=$(git diff --stat HEAD~${BEHIND} HEAD 2>/dev/null)
COMMIT_MSG=$(git log --oneline -${BEHIND} --format="%h %s")
```

根据变更范围判断是否需要 wiki-sync 或 repo-scanner（变更超 3 个 wiki 文件用 repo-scanner）。

### Step 6: 发送飞书通知

**必须执行**。用 `send_message` 工具发送到飞书群聊。

通知模板：

```
📦 仓库同步完成

分支: dev
远程新提交: {BEHIND} 个
本地未推送: {AHEAD} 个
状态: {已是最新 / 已拉取 / 有冲突}

{如果有新提交:}
最新提交:
{commit log 3-5 条}

{如果有冲突:}
⚠️ stash pop 有冲突，需手动处理:
{冲突文件列表}
```

**静默规则**：
- 已是最新 + 本地无 ahead → 仍然发通知（内容简短："已是最新，无新提交"）
- 有冲突 → 必须发告警

## 验证清单

- [ ] git fetch 成功
- [ ] stash 正确暂存和恢复
- [ ] pull --rebase 成功（或正确报告冲突）
- [ ] 飞书通知已发送
- [ ] wiki 已更新（如有新 commit）
