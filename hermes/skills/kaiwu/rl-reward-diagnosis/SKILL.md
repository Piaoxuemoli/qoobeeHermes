---
name: rl-reward-diagnosis
description: Diagnose RL agent behavioral issues by analyzing reward structure. Use when the agent exhibits unwanted behavior (random skills, wandering, avoiding combat, etc.) to identify root causes in the reward function.
version: 1.0.0
author: QoobeeHermes
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, rl, reward, diagnosis]
    related_skills: [rl-advisor, monitor-analyzer]
---

# RL Reward Diagnosis

诊断智能体行为问题的奖励结构根因。

## When to Use

- 智能体表现出"不合理"行为（乱放技能、徘徊、不打英雄、推塔慢等）
- 团队问"为什么智能体XXX"
- 训练监控中某个 reward 分项异常或 value_loss 某头异常高
- 评估奖励改动的效果

Don't use for: 训练数据抓取（用 monitor-analyzer）、代码位置查找（用 rl-advisor）

## 参考资料

- `references/region-examples.md` — 区域赛奖励诊断实例（乱放技能、徘徊、不打英雄、value_loss异常）
- `references/skill-whiff-rate-diagnosis.md` — 技能放空率100%的数据源缺失诊断

## 核心原则

**智能体永远在按奖励规则最优行动。** 如果行为"不合理"，问题一定在奖励结构，不在智能体本身。

## 诊断流程

### Step 1: 读取奖励配置

```python
# 读 conf.py 中的 REWARD_WEIGHT_DICT 和 SKILL_HIT_WEIGHT
# 读 reward_process.py 中的 get_reward() 理解计算方式
```

### Step 2: 对照行为分析信号

将奖励信号按"鼓励/惩罚"和"目标行为/实际行为"画成矩阵，找冲突。

### Step 3: 检查 value_loss 分项

如果某个 value_loss 分项异常高（其他头的10倍以上），说明该维度的值网络拟合失败。

## 常见行为问题诊断清单

详见 `references/reward-diagnosis.md`

## 监控指标异常诊断

行为问题之外，监控面板上的指标异常也需要诊断。典型模式：指标值为极端值（0%或100%），通常是数据源缺失而非智能体行为问题。

### 技能放空率 100%（skill_whiff_rate = 1.0）

**症状**：`skill_whiff_rate` 持续 1.0，`skill_hit_rate` 为 0，`skill_cast_rate` > 0。

**根因**：`hit_target_info` 字段在游戏帧数据中始终为空列表 `[]`。

**代码路径**：`train_workflow.py` `_append_skill_usage_metrics()` → `reward_process.py` `_skill_cast_hit_stats()` → 从 `hit_target_info` 提取命中技能槽集合，成功释放但不在命中集合中 → whiff。若 `hit_target_info` 恒为空 → 所有 cast 都被判为 whiff。

**结论**：数据源缺失问题，非智能体行为问题。放空率指标在此条件下无意义。

详见 `references/skill-whiff-rate-diagnosis.md`

| 检查项 | 位置 | 诊断标准 |
|--------|------|----------|
| 技能命中权重 | conf.py SKILL_HIT_WEIGHT | < 0.01 = 信号太弱 |
| 技能浪费惩罚 | reward_process.py | 缺失 = CD好了就放 |
| 技能落空惩罚 | reward_process.py | 缺失 = 打空无代价 |
| 敌方在射程特征 | hero_process.py | 缺失 = 难推算释放时机 |

**典型根因**：技能命中奖励极低(0.005~0.01)，无浪费/落空惩罚 → "放不放都一样" → 随便放

### 徘徊/往回跑（前后摇摆不定）

| 检查项 | 位置 | 诊断标准 |
|--------|------|----------|
| forward 权重 | conf.py | 过高 = 被推进奖励反复拉扯 |
| death_point 权重 | conf.py | 过重(如-1.0) + 战斗弱 = 恐惧回避 |
| 战斗奖励 | conf.py | 过弱 = 打不赢 → 被迫撤退 → 被forward拉回 |

**典型根因**：forward往前推，death往回拉，战斗能力不足撑不住前线 → 振荡

### 不打英雄（优先补刀/回避战斗）

| 检查项 | 位置 | 诊断标准 |
|--------|------|----------|
| kill_point 权重 | conf.py | **负值 = 直接惩罚击杀**（最致命） |
| death_point 权重 | conf.py | -1.0 + kill负值 = 打英雄双亏 |
| last_hit 权重 | conf.py | 远高于kill = 补刀比打架划算 |
| 技能命中权重 | SKILL_HIT_WEIGHT | < 0.01 = 打到英雄无感 |

**典型根因**：kill_point为负 + last_hit正奖励 → "打英雄亏本，补刀稳赚" → 回避战斗

### 推塔慢（不主动攻击防御塔）

| 检查项 | 位置 | 诊断标准 |
|--------|------|----------|
| attack_tower 权重 | conf.py | < 0.1 = 打塔信号弱 |
| tower_hp_point 权重 | conf.py | 过高 = 只关心己方塔 |
| forward 权重 | conf.py | 过高 = 只想往前走，不打塔 |

## value_loss 分项诊断

| 异常头 | 可能原因 |
|--------|----------|
| value_loss_econ 异常高 | money/exp权重太小但数据方差极大（累计值差分） |
| value_loss_hp 异常高 | hp权重过大或血量变化过于剧烈 |
| value_loss_tower 异常高 | tower_hp和forward信号冲突 |
| value_loss_combat 异常高 | combat子项太多，信号混杂 |

## 奖励改动效果评估

| 观察维度 | 指标 | 预期变化 |
|----------|------|----------|
| 目标行为是否增加 | 对应reward分项 | 上升 |
| 非目标行为是否减少 | 其他reward分项 | 不应大幅下降 |
| 胜率 | win_rate | 不应下降 |
| 值网络稳定性 | 对应value_loss | 不应飙升 |
| 对局时间 | episode_frame | 不应大幅增加 |

## 架构层面问题（非奖励能解决）

| 问题 | 根因 | 解法 |
|------|------|------|
| 技能方向不准 | 6个动作头独立采样，无条件依赖 | 架构改造：条件化动作头 |
| 非相关头梯度噪声 | 所有头都参与策略梯度 | IS_REINFORCE_TASK_LIST 设False |
| sub_action_mask未利用 | 方向头未被button类型过滤 | 用mask约束所有子动作头 |

## 区域赛奖励结构参考

conf.py REWARD_WEIGHT_DICT:
- hp_point: 2.0, tower_hp_point: 6.0, forward: 0.01
- money_point: 0.006, exp_point: 0.0055, ep_rate: 0.75
- last_hit: 0.5, attack_tower: 0.3, passive_stack: 0.0005
- kill_point: 0.2, death_point: -1.0

SKILL_HIT_WEIGHT:
- 鲁班: s1=0.045, s2=0.055, s3=0.0
- 狄仁杰: s1=0.03, s2=0.0, s3=0.2

特殊奖励: 狄仁杰解控0.15, 召唤师浪费-0.5
