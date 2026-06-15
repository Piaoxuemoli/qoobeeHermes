# Entropy Beta 衰减设计模式

## 设计原则

entropy_beta (熵正则化系数) 的衰减应与学习率衰减**同步**，使用同一个 `TARGET_STEP` 参数。

## 参考实现（区域赛 agent_ppo）

### conf.py 参数

```python
BETA_START = 0.015    # 初始值
BETA_END = 0.005      # 终值（保留少量探索）
# 衰减步数 = TARGET_STEP（与 LR 共用，不额外乘系数）
```

### algorithm.py 衰减逻辑

```python
# 在 learn() 中，scheduler.step() 之后
if self.train_step < self.target_step:
    progress = self.train_step / self.target_step
    self.model.var_beta = Config.BETA_START + (Config.BETA_END - Config.BETA_START) * progress
else:
    self.model.var_beta = Config.BETA_END
```

## 常见错误

- ❌ 用 `BETA_DECAY_STEPS * TARGET_STEP` 做总步数 — 与 LR 不同步，衰减节奏不一致
- ❌ 用指数衰减 — 容易突然压缩探索空间，线性更温和
- ❌ beta 不衰减 — 80 万步后持续满权重探索会阻碍精细化

## 何时开始衰减

- selfplay 下 win_rate 稳定 50%，train_step 已过训练中期
- entropy_loss 稳定（未崩塌也未爆开）
- 如果 entropy_loss 骤降到 -12 以下，反而需要**提高** beta

## 参考

- 区域赛 conf.py: `Config.BETA_START`, `Config.BETA_END`, `Config.TARGET_STEP`
- 区域赛 algorithm.py: `Algorithm.learn()` 中的 beta 衰减逻辑
- 区域赛 model.py: `self.var_beta` 用于 `loss = value_cost + policy_cost + var_beta * entropy_cost`
