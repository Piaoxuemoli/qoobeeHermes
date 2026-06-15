---
name: monitor-analyzer
description: Use when the user asks about training status, or when a cron alert fires. Fetches training monitoring data (including eval/matchup win rates and skill usage) from Tencent Arena API, runs anomaly detection, generates charts, keeps a per-run long-term record, and sends code-based analysis with prioritized recommendations via Feishu.
version: 3.0.0
author: Qoobee
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, monitoring, training, anomaly-detection]
    related_skills: [rl-advisor, repo-scanner]
---

# Monitor Analyzer

自动抓取开悟平台训练监控数据，结合代码分析训练状态，发送图表、长期趋势与排序建议。

代码与描述分离：脚本在 `scripts/`，详细指标解读/正常范围/输出模板在 [reference.md](reference.md)。

## When to Use

| 场景 | 触发方式 | 动作 |
|------|----------|------|
| 用户问 "看看训练状态" / "reward 怎么样" | 主动 | 完整分析（fetch + plot + report） |
| 用户给新 URL 或 token | 配置更新 | 解析参数 → 更新 config → 验证 |
| 用户说 "切换赛段" / "新训练开始了" | 配置更新 | 更新 config + 重新验证 |
| cron 写入 `data/alert.json` | 被动 | 自动 fetch + 分析，标注 "自动触发" |
| cookie 过期（validate 失败） | 被动 | 提示用户更新 token |

**Don't use for:** 代码审查（用 代码审查 skill）、超参建议（用 rl-advisor skill）。

## 执行规则

**所有步骤自动执行，不询问确认。** 直接运行命令、读文件、生成分析。仅在出错（token 过期、网络故障）时才向用户报告。所有脚本在 skill 的 `scripts/` 目录下运行。

## 执行流程

### Step 1: 检查告警（被动触发）

读 `data/alert.json`，若存在且 `status == "alert"`：标记 "自动触发：检测到训练异常"，列出所有 alert（metric/type/detail），继续后续步骤。无告警文件则跳过。

### Step 2: 抓取数据

```bash
cd scripts
python3 fetch.py --hours 6 --format structured
```

- `--format structured` 输出 JSON 摘要（含 avg/std/cv/trend，便于解析）
- 用户指定范围用 `--hours N`；只关心某组用 `--groups quick_check`
- 自动写 `data/latest.json`，并按 task_id 追加一条摘要到 `data/history/<task_id>.jsonl`

**抓取失败时：不要继续后续步骤，转「配置/鉴权恢复流程」。** fetch 会输出状态行 `✗ [status] ...` 并用不同退出码区分（status ∈ missing_config / token_expired / network_error / api_error）。需要机器判断时加 `--json` 取 `{"status","need","message"}`。

### Step 3: 生成图表

```bash
cd scripts
python3 plot.py --hours 6
```

输出到 `/tmp/monitor_charts/`：reward_trend / loss_curve / convergence / environment / **eval**（评估与对位胜率）/ **skill**（施放/命中/放空）/ **longterm**（当前运行长期趋势）。出错则跳过图表，用文字代替。

### Step 4: 长期趋势与诊断建议

```bash
cd scripts
python3 report.py --json --since 72h
```

输出当前训练运行的长期趋势（按 task_id 分桶，URL 变即新运行）+ 结构化 `findings`（status + 排序建议）。

### Step 5: 代码关联分析

读 `data/latest.json` 与 report 的 findings，对照 [reference.md](reference.md) 的指标解读框架与「症状→动作」决策表分析。**必须做到：**
1. 对照 conf.py 实际权重解释各分项贡献（勿凭印象）
2. 指出异常指标对应的代码逻辑
3. 给可操作建议（调哪个参数、为什么）
4. 区分正常波动与真正异常（selfplay 下看胜率而非 reward_sum）

### Step 6: 组装输出

按 [reference.md](reference.md) 的飞书输出模板组织：状态结论 → 核心指标 → 评估/对位 → Reward 分项 → Loss 与稳定性 → 技能使用 → 长期趋势 → 异常 → 结论与建议 → MEDIA 图片。**不用表格**；图片末尾 `MEDIA:` 前缀逐行嵌入。

## 配置/鉴权恢复流程（主动检测 → 告知 → 更新 → 验证 → 继续）

当 fetch / validate 返回非 ok 状态时，**主动**按 `status` 分支处理；不要把失败当无数据糊弄过去。所有命令在 `scripts/` 下运行。

判定状态（任选其一）：
```bash
cd scripts
python3 fetch.py --validate --json   # 输出 {"status","need","message",...}
```

退出码：ok=0 / missing_config=3 / token_expired=4 / network_error=5 / api_error=6。

### status == token_expired（need: token）
向用户说明并索要：**"训练 token 已过期，请提供新的 kaiwu-token（浏览器 → 开悟监控页 → Cookie 里的 kaiwu-token）。"**
拿到后：
```bash
cd scripts
python3 fetch.py --update-config --token "<NEW_TOKEN>" --json
python3 fetch.py --validate --json
```
validate 返回 ok → 回到 Step 2 继续；仍 token_expired → 告知 token 可能复制有误，请重取。

### status == missing_config（need: url[, token]）
向用户说明并索要：**"需要本次训练的监控页面 URL（含 task_id/team_id/domain_id/exp_id），请从开悟监控页地址栏复制完整 URL。"**（若同时缺 token，一并索要）
拿到后：
```bash
cd scripts
python3 fetch.py --update-config --url "<完整URL>" --json   # 若同时缺 token 再加 --token "<TOKEN>"
python3 fetch.py --validate --json
```
- update 输出含 `missing_fields`：非空说明 URL 仍没带齐参数（可能只复制了片段），需让用户提供完整 URL。
- URL 变即新训练运行，history 自动开新桶（`data/history/<task_id>.jsonl`）。
- validate ok → 回到 Step 2。

### status == network_error
告知用户网络无法连接开悟平台，请检查网络/VPN 后重试。**不要反复重试或改 token。**

### status == api_error
报告返回的 `code` 与 `msg`，提示可能是任务参数（task_id/exp_id 等）不匹配，请核对 URL。

### 赛段切换
```bash
cd scripts
python3 fetch.py --update-config --stage 全国决赛
```
→ "已切换。请提供新训练的 URL。"（随后走 missing_config 分支补 URL）

## Cron 配置

异常检测由系统 cron 每 30 分钟运行（路径为 skill 内 scripts）：

```bash
*/30 * * * * cd /path/to/Kaiwu_2026/.hermes/skills/kaiwu/monitor-analyzer/scripts && python3 check.py --json >> ../data/check.log 2>&1
```

- 阈值：reward 1h 降 50%、loss spike 10x、胜率 4h 停滞、eval 胜率 4h 降 30%、value_loss_tower spike 8x、skill_whiff_rate >0.5、reward_sum/policy_loss 震荡(cv)
- 异常写 `data/alert.json`，无异常清除；告警文件持久化（不在 /tmp）

## 注意事项

- 训练云端运行 168h，短期波动正常，勿过度解读小波动
- token 随训练变化，每次新训练需更新
- `config.local.yaml` 与 `data/` 含敏感/运行时数据，不提交 git
- 用户没明确问训练状态时，不要主动触发
- 分析必须对照 conf.py 实际参数值（见 reference.md），不凭印象
