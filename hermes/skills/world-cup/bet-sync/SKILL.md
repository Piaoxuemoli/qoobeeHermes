---
name: bet-sync
description: Sync betting data from agents/*/round-N/bets.md into the HTML file's AI_ROUNDS array. Parses each model's bets.md, extracts bet entries, deploys to Caddy.
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [world-cup, sync, bets, html]
    related_skills: [lottery-updater]
---

# Bet Sync

从各模型 agent 的 `bets.md` 文件同步投注方案到 HTML。

## When to Use

| 场景 | 触发方式 | 动作 |
|------|----------|------|
| 新一轮投注方案就绪 | 主动/被动 | 解析 bets.md → 同步到 HTML |
| 用户说 "同步投注" | 主动 | 执行同步流程 |
| 用户说 "某模型的方案改了" | 主动 | 重新同步该模型 |

## 执行流程

### Step 1: 拉取最新代码

```bash
cd ~/world-cup && git pull origin main
```

### Step 2: 运行同步脚本

```bash
python3 ~/world-cup/.hermes/skills/world-cup/lottery-updater/scripts/sync_bets.py --round N
```

### Step 3: 更新数据文件

**当前架构（纯 HTML）：**

数据直接编辑 `~/world-cup/世界杯预测.html` 中的 `AI_ROUNDS` JavaScript 数组（约第 2492 行）。

同步规则：
- bets.md 中的组合对应过关票：第一条 bet 的 `amount > 0`，后续 legs 的 `amount = 0`
- 单关的 `过关: '单关'`
- `actualScore` / `result` / `prize` 留空/`'pending'`/`0`，等赛后填

### Step 4: 部署

```bash
cd ~/world-cup
cp 世界杯预测.html index.html
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@worldcup2026" \
  add 世界杯预测.html index.html
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@worldcup2026" \
  commit -m "sync(round-N): 同步各模型投注方案"
# git push 需要 GitHub 认证，当前服务器未配置，仅本地提交

# 部署到 Caddy（唯一可用 Web 服务）
docker cp ~/world-cup/index.html colosseum-caddy-1:/srv/world-cup/index.html
docker exec colosseum-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

## 注意事项

1. 各模型 bets.md 格式不完全统一，需人工核对转换结果
2. Deepseek 的 v4 方案已排除 M1/M2（已过截止时间）
3. 同步后必须 `cp 世界杯预测.html index.html` + `docker cp` 到 Caddy 才对外生效
4. 大文件（>2000行）处理时用 `patch()` 工具逐条修改，避免覆盖整个文件
5. **架构说明**：项目为纯 HTML 单文件应用（~3000行），无 React/Vite/npm
