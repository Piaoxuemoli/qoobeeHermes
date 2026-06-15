---
name: repo-sync
description: Sync world-cup repo from GitHub, update nginx-served HTML, and reload. Used when pulling latest changes or deploying updates.
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [world-cup, git, deploy, nginx]
    related_skills: [lottery-updater, bet-sync]
---

# Repo Sync

同步 GitHub 仓库并部署到 nginx。

## When to Use

| 场景 | 动作 |
|------|------|
| 用户说 "部署" / "更新页面" | git pull → cp → reload |
| 用户说 "同步代码" | git pull |
| 部署新投注方案后 | cp html → reload |

## 执行流程

```bash
cd ~/world-cup && git pull origin main
cp 世界杯预测.html index.html
nginx -s reload
```

验证：`curl -sI http://localhost:8080/ | head -5`

## 注意事项

- 确保 `index.html` 与 `世界杯预测.html` 始终同步
- nginx 以 root 用户运行，配置在 `/etc/nginx/conf.d/worldcup.conf`
