# 超参数衰减调度 — 实现模式

## LR Schedule（参考模板）

KaiwuDRL 框架使用 PyTorch `LambdaLR`，定义在 `agent_ppo/agent.py`：

```python
# conf.py
INIT_LEARNING_RATE_START = 4e-5
TARGET_LR = 3e-5
TARGET_STEP = 5000  # 衰减完成的 train_step 数

# agent.py
self.scheduler = LambdaLR(self.optimizer, lr_lambda=self.lr_lambda)

def lr_lambda(self, step):
    if step > self.target_step:
        return self.target_lr / self.lr
    else:
        return 1.0 - ((1.0 - self.target_lr / self.lr) * step / self.target_step)
```

`step` = `algorithm.train_step`，每次 `learn()` 调用 +1。

## Entropy Beta Schedule（已实现）

**文件**：`conf/conf.py` + `algorithm/algorithm.py`

```python
# conf.py
BETA_START = 0.015
BETA_END = 0.005
# 注意：没有 BETA_DECAY_STEPS，直接用 TARGET_STEP，与 LR 完全同步

# algorithm.py (在 scheduler.step 之后)
if self.train_step < self.target_step:
    progress = self.train_step / self.target_step
    self.model.var_beta = Config.BETA_START + (Config.BETA_END - Config.BETA_START) * progress
else:
    self.model.var_beta = Config.BETA_END
```

**关键**：`model.var_beta` 在 `model.compute_loss()` 中使用：
```python
self.loss = self.value_cost + self.policy_cost + self.var_beta * self.entropy_cost
```

## 模式总结

新增超参数衰减的步骤：
1. `conf.py` 添加 `XXX_START` 和 `XXX_END` 两个参数
2. **不要添加 `XXX_DECAY_STEPS`**，直接复用 `TARGET_STEP`，与 LR 同步
3. `algorithm.py` 的 `learn()` 方法中，`self.scheduler.step()` 之后添加线性衰减逻辑
4. 衰减逻辑：`progress = train_step / target_step`，线性插值
5. 如果参数在 `model` 上（如 `var_beta`），修改 `self.model.xxx`
6. 确认 `train_step` 是否从预训练 checkpoint 恢复（否则衰减会重置）

## 注意事项

- **新调度必须对齐已有模式** — LR 用 `TARGET_STEP`，新参数就用 `TARGET_STEP`，不要发明新乘数
- 预训练加载时 `train_step` 可能重置为 0，需要确认框架行为
- `var_beta` 是模型属性，checkpoint 保存时应包含，但 `train_step` 在 algorithm 中，可能不一致
- 线性衰减足够，不需要指数/cosine 等复杂调度
