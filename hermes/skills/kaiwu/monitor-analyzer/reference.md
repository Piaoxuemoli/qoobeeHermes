# monitor-analyzer 参考

指标解读框架、正常范围、评估/技能解读、症状→动作决策表、飞书输出模板。
权重值对齐 `区域赛/工程/agent_ppo/conf/conf.py`，改 conf 后需同步此文件。

## 指标解读参考

### Reward 子项（对应 4 个 value head）

- **reward_hp** — 生存。hp_point(2.0) + ep_rate(0.75)，零和 delta。持续偏低=频繁掉血或能量管理差。
- **reward_tower** — 推进。tower_hp_point(6.0) + forward(0.01) + attack_tower(0.35)。tower_hp_point 权重最高且最稀疏，是 reward_tower 方差的主要来源；forward 用势函数 v3（Δφ + 优势加成），attack_tower 为单侧敌方塔掉血。
- **reward_econ** — 经济。money_point(0.006) + exp_point(0.0055) + last_hit(0.5)。last_hit 是核心驱动。
- **reward_combat** — 战斗。kill_point(0.5) + 技能命中(英雄特定) + passive_stack(0.0005) + death_point(-1.0) + cleanse(0.15) + summoner_waste(-0.5) + 技能乱放惩罚(SKILL_WHIFF_WEIGHT，当前 -0.05)。death 是最大的负向约束。
- **reward_sum** = hp + tower + econ + combat，用于 GAE 优势计算。

技能命中权重（SKILL_HIT_WEIGHT）：鲁班 {1:0.045, 2:0.055, 3:0}；狄仁杰 {1:0.03, 3:0.2}。

### 正常范围参考（selfplay 对称博弈）

- win_rate / episode_win_value: 0.45~0.55 正常（selfplay 基线 50%）。**对称自对弈下应优先看胜率，而非 reward_sum 绝对值。**
- reward_sum: 缓慢上升或稳定；零和项在自对弈下期望≈0，短期围绕基线抖动正常；骤降 >30% 需关注。
- total_loss: 单调或波动下降；spike >5x 需关注。
- policy_loss: 0.1~2.0；持续偏高或高波动=策略震荡。
- entropy_loss: 随训练下降正常（策略趋于确定）。
- grad_norm: <10 正常；飙高=梯度爆炸。
- entropy_beta: 从 0.015 线性衰减到 0.005（BETA_DECAY_STEPS 内），之后稳定。
- 波动系数 cv = std/|avg|：用于判断震荡，reward_sum/policy_loss 的 cv 持续偏大才值得动手。

### 评估与对位解读

- **eval_luban_win_rate / eval_direnjie_win_rate**：评估对局（exploit 策略 vs 对手）的胜率，比 selfplay 训练胜率更能反映真实强度。持续 <0.45 表示该英雄处于劣势。
- **luban/direnjie_summoner_win_rate**：按英雄统计的召唤师对局胜率。
- **direnjie_vs_luban / luban_vs_direnjie_win_rate**：跨英雄对位胜率，用于判断英雄间强弱与 counter 关系。
- eval 胜率与 selfplay 胜率差异大时：selfplay 高但 eval 低 = 过拟合自身策略，泛化差。

### 技能使用解读

- **skill_cast_rate**：每局 1/2/3 技能施放次数。被乱放惩罚压到接近 0 = 模型不敢放技能，丢 DPS，需放松惩罚。
- **skill_hit_rate**：命中数/施放数。越高越好。
- **skill_whiff_rate**：放空数/施放数。高位（>0.5）= 乱放未收敛。
- 判读「乱放」是否改善：看 skill_whiff_rate 下降且 skill_cast_rate 未塌陷。

### 代码参考路径

- `区域赛/工程/agent_ppo/conf/conf.py` — 所有权重和超参（含 SKILL_WHIFF_WEIGHT、CLIP_PARAM_HIGH 等）
- `区域赛/工程/agent_ppo/feature/reward_process.py` — reward 计算（4 子项分组、势函数 v3、零和、技能乱放检测）
- `区域赛/工程/agent_ppo/model/model.py` — 多头价值、compute_loss（value_cost 各头平均）
- `区域赛/工程/agent_ppo/workflow/train_workflow.py` — 训练流程与监控上报

## 症状 → 候选动作 决策表

`report.py` 按此表产出排序建议；分析时据此给可操作建议（指出调哪个参数、为什么）。

- value_loss_tower 显著大于其它头（>2x 均值）→ 多头价值尺度不均衡，tower 头主导共享 trunk 梯度。compute_loss 给各头按尺度加系数，或下调 tower_hp_point(6.0)。checkpoint 安全。
- skill_whiff_rate 高位(>0.5) → 乱放未收敛，上调 SKILL_WHIFF_WEIGHT(-0.05)；盯 skill_cast_rate 不要塌到 0。
- eval_*_win_rate 持续 <0.45 → 对位劣势，结合 vs 对位胜率定位吃亏对象，针对性调奖励/课程。
- reward_sum / policy_loss 波动系数 cv 偏大 → 先确认是否自对弈固有抖动（看胜率）；policy_loss 持续高波动可收回 clip-higher(CLIP_PARAM_HIGH 0.28→0.2)。
- grad_norm >10 → 确认 GRAD_CLIP_RANGE(0.5) 生效，排查奖励尖峰。
- win_rate 长期停滞(<1% 变化) + loss 已收敛 → 可能进入瓶颈，考虑课程/对手池更新或奖励重塑。

## 飞书输出模板

适配飞书 markdown：**不要用表格**（会显示空白）；标题(#)+列表(-)+粗体(**)；代码块用围栏。
图片在末尾用 `MEDIA:` 前缀逐行嵌入，gateway 自动上传，不要写"图表已发送"。

```markdown
# 训练监控分析

**赛段**: 区域赛 | **task_id**: 183628 | **状态**: 正常 / 需关注 / 异常

## 状态结论
- 一句话总体判断（结合胜率，而非只看 reward_sum）

## 核心指标
- **win_rate**: avg=0.52, 趋势 +3% (6h)
- **reward_sum**: avg=12.30, 趋势 +8%, cv=0.4
- **total_loss**: avg=0.45, 趋势 -12%

## 评估与对位
- **eval_luban_win_rate**: 0.51 / **eval_direnjie_win_rate**: 0.48
- **对位**: direnjie_vs_luban 0.55 / luban_vs_direnjie 0.45

## Reward 分项
- **reward_hp**: avg=3.20（hp*2.0 + ep*0.75）
- **reward_tower**: avg=5.10（tower_hp*6.0 + forward*0.01 + attack_tower*0.35）
- **reward_econ**: avg=2.80（money*0.006 + exp*0.0055 + last_hit*0.5）
- **reward_combat**: avg=1.20（kill*0.5 - death*1.0 + 技能命中 - 乱放*0.05）

## Loss 与稳定性
- **policy_loss**: avg=0.85, cv=0.6
- **value_loss_tower**: avg=0.18（与其它头对比，判断是否主导）
- **grad_norm**: 3.2 / **entropy_beta**: 0.008

## 技能使用
- **skill_cast_rate**: 6.2/局 / **skill_hit_rate**: 0.42 / **skill_whiff_rate**: 0.58

## 长期趋势（当前训练运行）
- reward_sum: 8.1 → 12.3（+52%, train_step 40w→80w）
- skill_whiff_rate: 0.71 → 0.58（乱放改善中）

## 异常检测
（无异常 / 列出具体异常）

## 结论与建议
1. [warning] value_loss_tower 是其它头 3.1x → 多头不均衡，建议 compute_loss 加尺度系数
2. [info] reward_sum cv=0.9 偏大 → 多为自对弈固有抖动，优先看胜率

MEDIA:/tmp/monitor_charts/reward_trend.png
MEDIA:/tmp/monitor_charts/loss_curve.png
MEDIA:/tmp/monitor_charts/eval.png
MEDIA:/tmp/monitor_charts/skill.png
MEDIA:/tmp/monitor_charts/convergence.png
MEDIA:/tmp/monitor_charts/environment.png
MEDIA:/tmp/monitor_charts/longterm.png
```
