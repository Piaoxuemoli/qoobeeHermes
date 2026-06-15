---
name: lottery-updater
description: Automatically fetch match results from ESPN API and update the HTML display page. Covers result fetching, bet settlement, HTML patching, and Caddy deployment.
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [world-cup, lottery, odds, results, html-update]
    related_skills: [bet-sync]
---

# Lottery Updater

自动拉取体彩竞彩足球赔率与赛果，更新 HTML 展示页面。

## When to Use

| 场景 | 触发方式 | 动作 |
|------|----------|------|
| 用户说 "更新赔率" / "拉取最新赔率" | 主动 | 抓取竞彩赔率 → 更新 HTML |
| 用户说 "更新赛果" / "比赛结果出来了" | 主动 | 抓取赛果 → 更新 AI_ROUNDS result/prize |
| 用户说 "同步投注" / "同步bets" | 主动 | 从 agents/*/round-N/bets.md 同步到 HTML |
| cron 定时触发 | 被动 | 自动检查是否有已结束比赛需更新 |
| 用户说 "刷新页面" | 主动 | npm run build + 部署到 nginx/Caddy |

**Don't use for:** 修改投注策略（由各模型 agent 完成）、创建新的 round 目录（由人工触发）。

## 数据源

### 赔率来源
1. **中国竞彩网** (sporttery.cn) — 官方赔率，最权威
2. **500彩票网** (500.com) — 竞彩赔率备用源
3. **oddspedia.com** — 国际赔率对比参考

### 赛果来源
1. **ESPN API** (已验证可用) — 主要数据源，见下方 API 详情
2. **FIFA 官方** (fifa.com) — 权威备选
3. **懂球帝 / 虎扑** — 中文快速源

#### ESPN API 详情（2026-06-13 验证）

**可用端点：**
```
https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD
```

**⚠️ 关键陷阱：** `fifa.world.cup.26` 端点返回 400 错误，必须用 `fifa.world`。

**请求要求：**
- 必须加 header `Accept-Encoding: identity`（否则返回 gzip 乱码）
- 日期格式：`YYYYMMDD`（UTC 日期，非北京时间）

**响应解析：**
```python
import json
with open('response.json') as f:
    data = json.load(f)
for e in data.get('events', []):
    name = e['name']                          # "Bosnia-Herzegovina at Canada"
    date = e['date']                          # "2026-06-12T19:00Z" (UTC)
    status = e['status']['type']['name']      # "STATUS_FULL_TIME"
    detail = e['status']['type']['shortDetail']  # "FT" / "2'" / "Scheduled"
    for c in e['competitions'][0]['competitors']:
        team = c['team']['displayName']       # "Canada"
        score = c['score']                    # "1"
        side = c['homeAway']                  # "home" / "away"
```

**时区注意：** API 按 UTC 日期分组。UTC 19:00 的比赛在 UTC 日期次日 01:00 结束时仍归入原日期。北京时间 = UTC+8，需自行转换。

**已验证的 2026 世界杯数据（6/12-6/13）：**
- 6/11 UTC: Mexico 2-0 South Africa (M1), South Korea 2-1 Czechia (M2)
- 6/12 UTC: Canada 1-1 Bosnia (M3), USA vs Paraguay in progress (M5)
- 6/13 UTC: Qatar vs Switzerland, Brazil vs Morocco, Haiti vs Scotland (均 Scheduled)

## Pitfalls

1. **ESPN API 端点陷阱（已修复 2026-06-13）**：`fetch_results.py` 之前用 `/fifa.world` 基础URL会返回404。正确端点是 `/fifa.world/scoreboard?dates=YYYYMMDD`。脚本已修复，如果手动调用curl务必用正确端点。

2. **ESPN API JSON 控制字符（2026-06-15 发现）**：某些日期（如6/14）的 API 响应包含非法控制字符，导致 `json.loads()` 抛出 `Invalid control character` 错误。**解决方案**：先 `curl -o /tmp/espn_YYYYMMDD.json`，再用 Python 读取文件解析，不要 pipe 到 Python。某些日期 pipe 到 python3 会返回空输出。
   ```bash
   # 正确做法：先存文件再解析
   curl -s -H "Accept-Encoding: identity" "https://...scoreboard?dates=20260614" -o /tmp/espn_0614.json
   python3 -c "import json; data=json.load(open('/tmp/espn_0614.json')); ..."
   ```

3. **比赛中状态检测（2026-06-15 发现）**：比赛可能处于 `STATUS_SECOND_HALF`（如 90'+6'）而非 `STATUS_FULL_TIME`。初次查询未结束的比赛需等待后重新检查。晨报流程中应对所有 `status != STATUS_FULL_TIME` 的比赛做二次确认（等待30秒后重查）。

4. **批量更新模式（推荐）**：当同一场比赛（如M5）出现在多个模型的多个过关票中时，用 Python 脚本 `str.replace()` 批量更新比逐个 patch 高效得多。**关键**：同一 matchId 可能出现多次（不同 amount/odds/pick），必须用完整 bet 行字符串做唯一匹配（组合 matchId + amount + odds + playType + pick）。
   ```python
   # 推荐模式：用完整 bet 行字符串做 replace
   old = "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '胜平负', pick: '主胜', amount: 60, odds: 1.12, 过关: '2×1', actualScore: '', result: 'pending', prize: 0 }"
   new = "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '胜平负', pick: '主胜', amount: 60, odds: 1.12, 过关: '2×1', actualScore: '7:1', result: 'win', prize: 0 }"
   content = content.replace(old, new)
   # 注意：同一 pattern 可能出现在 gpt55 和 kimi 中（相同赔率/金额），replace 会同时更新两者
   ```

5. **让球胜平负判定**：主队得分 + 让球数后比较。如 美国4-1巴拉圭，pick: 让平(-1) → 调整后 3-1 → 美国胜 → loss（因为pick是让平）。德国7-1库拉索，pick: 让胜(-3) → 调整后 4-1 → 德国胜 → win。

6. **过关票结构解析（2026-06-15 验证）**：bets 数组中，连续的 bet 行通过 `过关` 字段分组为一张票。第一行 `amount > 0` 是主腿（代表整张票金额），后续 `amount = 0` 是配腿。同一张票的所有腿共享相同的 `过关` 标签（如 '2×1'）但可能不相邻——需按顺序配对。
   - **结算时机**：配腿（amount=0）的结果也需要更新，但 prize 只在主腿行计算
   - **已判负票**：如果任一腿已 loss，即使其他腿 pending，整张票已确定 loss，prize=0
   - **已判胜票**：所有腿都 win 时，prize = 赔率连乘 × amount

## 执行流程

### Step 1: 拉取最新代码

```bash
cd ~/world-cup && git pull origin main
```

### Step 2: 抓取赔率（赛前）

```bash
python3 ~/world-cup/.hermes/skills/world-cup/lottery-updater/scripts/fetch_odds.py --round N
```

输出格式：
```json
{
  "round": 1,
  "matches": [
    {"matchId": "M3", "home": "加拿大", "away": "波黑", "odds": {"win": 2.20, "draw": 3.10, "lose": 2.90}}
  ]
}
```

赔率更新到 HTML 中对应 bet 的 odds 字段。

### Step 3: 抓取赛果（赛后）

```bash
python3 ~/world-cup/.hermes/skills/world-cup/lottery-updater/scripts/fetch_results.py --round N
```

输出格式：
```json
{
  "round": 1,
  "results": [
    {"matchId": "M3", "score": "2:1", "home": "加拿大", "away": "波黑"}
  ]
}
```

### Step 4: 更新数据

**当前架构（纯 HTML）：**

数据文件：`~/world-cup/世界杯预测.html`（约 3000 行的单文件应用，JS + HTML 一体）

`AI_ROUNDS` 数组位于文件约第 2492 行，结构：
```javascript
const AI_ROUNDS = [
  {
    round: 1,
    title: '小组赛第1轮',
    status: 'active',  // 'active' | 'completed'
    predictions: {
      gpt55: { bets: [ { match, matchId, playType, pick, amount, odds, 过关, actualScore, result, prize } ] },
      glm51: { ... }, qwen37: { ... }, deepseek: { ... }, mimo: { ... }, kimi: { ... }
    }
  }
];
```

更新步骤：
1. 用 `patch()` 工具逐条更新对应 matchId 的 bet
2. 设置 `actualScore` 为实际比分（如 `'1:1'`）
3. 设置 `result`：`'win'` 或 `'loss'`
4. 过关票：需等所有腿都结束才能计算整张票 result 和 prize
5. 单关：直接判定
6. 若该轮所有 bet 都有结果 → 将 round status 改为 `'completed'`

**让球胜平负判定：** 主队得分 + 让球数后比较。如 加拿大1-1波黑，pick: 让平(-1) → 调整后 0-1 → 波黑胜 → loss。

### Step 5: 同步 agents 投注方案（可选）

如有新的 bets.md 需要同步到 HTML，使用 bet-sync skill 的流程。
手动方式：读取 `agents/{model}/round-N/bets.md`，转换为 `AI_ROUNDS` 格式后用 `patch()` 写入 HTML。

### Step 6: 提交变更

**当前架构（纯 HTML 文件，非 React）：**

数据直接编辑 `~/world-cup/世界杯预测.html` 中的 `AI_ROUNDS` JavaScript 数组。无 React 前端、无 `rounds.ts`、无需 `npm run build`。

```bash
cd ~/world-cup
cp 世界杯预测.html index.html
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@worldcup2026" \
  add 世界杯预测.html index.html
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@worldcup2026" \
  commit -m "feat(results): 更新第N轮赛果"
# git push 需要 GitHub 认证，当前服务器未配置，仅本地提交
```

**⚠️ Git 认证陷阱：** 服务器无 `~/.git-credentials`，`git push` 会失败。本地 commit 成功即可，不要把 push 失败当作错误。

### Step 7: 部署到 Caddy

**⚠️ 运行时状态（2026-06-13 确认）：**
- **Caddy (Docker, 端口 80)** — ✅ 唯一正常运行的 Web 服务
- **nginx (端口 8080)** — ❌ 已停止（`Active: failed`），不可用

```bash
# 唯一有效的部署方式
docker cp ~/world-cup/index.html colosseum-caddy-1:/srv/world-cup/index.html
docker exec colosseum-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

**验证：**
```bash
# 在 Caddy 容器内检查文件已更新
docker exec colosseum-caddy-1 grep "actualScore" /srv/world-cup/index.html | head -5
```

**外部访问：** http://43.156.230.108/ (Caddy 端口 80) — nginx 8080 端口不可用。

## 赔率计算公式

### 单关奖金（最常见）
```
奖金 = 赔率 × 投注金额
```
例：amount=12, odds=1.80 → prize = 1.80 × 12 = 21.60

### 过关票奖金
```
奖金 = 腿1赔率 × 腿2赔率 × ... × 腿N赔率 × 投注金额
```
注意：过关票必须等所有腿都结束才能计算整张票 prize。只更新已完成腿的 result，prize 留 0。

### 关键陷阱
- HTML 中 `amount` 字段就是投注金额（元），不是倍数
- 过关票的 amount 只计入一次（整张票的总投注），不是每腿都有 amount
- 过关票中 amount=0 的腿是"配腿"，不单独计算奖金

### 结果判定
- **胜平负**：主胜/平/客胜 → 比对 pick 字段
- **让球胜平负**：根据让球数调整比分后判定
- **过关票**：所有腿都 win → 整张票 win；任一腿 loss → 整张票 loss
- **单关**：只看单场结果

## HTML 数据结构参考

```javascript
const AI_ROUNDS = [
  {
    round: 1,
    title: '小组赛第1轮',
    dateRange: '6月12日 — 6月18日',
    status: 'active',
    predictions: {
      deepseek: {
        analysis: '...',
        strategy: '...',
        bets: [
          {
            match: '德国 vs 库拉索',
            matchId: 'M9',
            playType: '胜平负',
            pick: '主胜',
            amount: 60,
            odds: 1.12,
            过关: '2×1',
            actualScore: '4:0',
            result: 'win',
            prize: 104.40,
          },
        ],
      },
    },
  },
];
```

## 注意事项

1. **购彩时间**：体彩店销售时间 11:00-22:00（工作日）/ 11:00-23:00（周末），早于开赛5-30分钟停售
2. **赔率变动**：竞彩赔率随投注量浮动，以出票时为准
3. **北京时间**：所有时间使用北京时间（UTC+8）
4. **M1/M2 已截止**：第1轮 M1(6/12 03:00) 和 M2(6/12 06:00) 早于购彩时间17:00，不可购买
5. **纯 HTML 架构**：项目为单文件 `世界杯预测.html`，无 React/Vite/npm，`world-cup-app/` 目录不存在
6. **matchId 无映射表**：HTML 中无 matchId→比赛名称/时间的映射，需从 `agents/*/round-1/bets.md` 反推
7. **过关票结算时机**：2×1 过关票需两腿都结束才能算 prize，只更新已完成腿的 result，prize 留 0

## Cron 配置

可配置定时任务自动检查赛果：

```bash
# 每2小时检查一次是否有新赛果（比赛日）
0 */2 * * * python3 ~/world-cup/.hermes/skills/world-cup/lottery-updater/scripts/fetch_results.py --auto-update
```

## 每日晨报流程（cron 09:00 触发）

当作为定时报告执行时，按以下步骤操作：

1. **确定时间窗口**：昨天 09:00 ~ 今天 09:00（北京时间）= 昨天 01:00 ~ 今天 01:00 (UTC)
2. **拉取赛果**：用 ESPN API 获取相关 UTC 日期的所有比赛。北京时间 09:00 的晨报需拉取 **昨天UTC + 今天UTC + 明天UTC** 三天数据（覆盖所有可能在窗口内结束的比赛）。
   ```python
   # 推荐模式：先存文件再解析（避免控制字符问题）
   for date in ['YYYYMMDD_yesterday', 'YYYYMMDD_today', 'YYYYMMDD_tomorrow']:
       terminal(f'curl -s -H "Accept-Encoding: identity" "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}" -o /tmp/espn_{date}.json')
       # 然后 python3 读取文件解析
   ```
3. **二次确认**：对所有 `status != STATUS_FULL_TIME` 的比赛（如 `STATUS_SECOND_HALF`），等待30秒后重新拉取确认最终结果
4. **匹配 matchId**：从 `AI_ROUNDS` 中提取所有 matchId 及对应比赛名称，与 ESPN 结果比对
5. **更新 HTML**：用 Python 脚本批量 `str.replace()` 更新已结束比赛的 bet（actualScore + result），一次脚本处理所有变更
   - 单关：直接填入 prize（amount × odds）
   - 过关票：更新已完成腿的 result，只有当所有腿都有结果时才计算整张票 prize
6. **部署**：cp → docker cp → caddy reload
7. **生成报告**：
   - 📅 时间窗口
   - ⚽ 已完成比赛及比分
   - 🏆 各模型命中/未命中（过关票逐腿分析）
   - 💰 已结算奖金和排名（含待开奖金额）
   - ⏳ 进行中/未开赛比赛
8. **Git commit**：`feat(results): 更新第N轮XX赛果`

**报告格式要点：**
- 过关票只更新已完成腿的 result，prize 在所有腿结束后才计算
- 对于同一 matchId 出现在多个过关票中的情况，逐票分析
- 明确标注哪些是"已确认损失"vs"待开奖"
- 排行榜需同时显示"确认资产"和"待开奖金额"

**已验证日期映射（2026世界杯）：**
| 北京时间 | UTC 日期 | ESPN API dates 参数 |
|----------|----------|---------------------|
| 6/14 09:00 ~ 6/15 09:00 | 6/13 01:00 ~ 6/14 01:00 UTC | 20260613, 20260614, 20260615 |
