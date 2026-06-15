# 技能放空率 100% 诊断

## 症状

监控面板 `skill_hit_whiff_rate` 显示：
- `skill_whiff_rate` = 1.0（100%）
- `skill_hit_rate` = 0
- `skill_cast_rate` > 0（有技能施放）

## 根因

`hit_target_info` 字段在游戏帧数据中始终为空列表 `[]`。

## 代码路径（按调用顺序）

### 1. 监控上报 — `train_workflow.py` L226-241

```python
def _append_skill_usage_metrics(self, monitor_data, monitor_side):
    agent = self.agents[monitor_side]
    reward_manager = getattr(agent, "reward_manager", None)
    cast = float(getattr(reward_manager, "skill_cast_total", 0.0))
    hit = float(getattr(reward_manager, "skill_hit_total", 0.0))
    whiff = float(getattr(reward_manager, "skill_whiff_total", 0.0))
    monitor_data["skill_cast_rate"] = round(cast, 2)
    if cast > 0.0:
        monitor_data["skill_hit_rate"] = round(hit / cast, 4)
        monitor_data["skill_whiff_rate"] = round(whiff / cast, 4)  # whiff == cast → 1.0
```

### 2. 每帧累计 — `reward_process.py` L569-573

```python
m_cast, m_hit, m_whiff = self._skill_cast_hit_stats(main_hero)
self.skill_cast_total += m_cast
self.skill_hit_total += m_hit
self.skill_whiff_total += m_whiff
```

### 3. 核心判定 — `reward_process.py` L620-642

```python
def _skill_cast_hit_stats(self, hero):
    hit_slots = set()
    for hit in self._as_dict_list(hero.get("hit_target_info", [])):
        st = hit.get("slot_type")
        if st in (1, 2, 3):
            hit_slots.add(st)
    cast = 0.0
    whiff = 0.0
    for s in hero.get("skill_state", {}).get("slot_states", []):
        st = s.get("slot_type")
        if st in (1, 2, 3) and s.get("succUsedInFrame", 0) > 0:
            cast += 1.0
            if st not in hit_slots:  # ← hit_slots 为空时所有 cast 都被判 whiff
                whiff += 1.0
    return cast, cast - whiff, whiff
```

## 逻辑链条

```
hit_target_info = []        # 游戏帧数据
  → hit_slots = set()        # 命中技能槽集合为空
    → st not in hit_slots     # 恒为 True
      → whiff = cast          # 所有施放都被判为放空
        → whiff / cast = 1.0  # 放空率 100%
```

## 排查方法

1. **确认数据源**：打印一帧 `hero.get("hit_target_info")` 确认是否为空
2. **查数据协议**：`参考资料/区域赛/官方资料/数据协议.md` → `HitTargetInfo` 定义
3. **查环境示例**：`参考资料/区域赛/环境返回json.txt` 中 `hit_target_info` 普遍为 `[]`

## 结论

这是**数据源缺失**问题，不是智能体行为问题。`hit_target_info` 字段可能未被游戏引擎填充，在此条件下 `skill_whiff_rate` 指标无参考价值。

## 适用范围

- 仅影响监控指标，不影响奖励计算（`_calc_skill_whiff` 同样依赖 `hit_target_info`，但奖励权重 `SKILL_WHIFF_WEIGHT` 可能为 0）
- `skill_hit_rate` 和 `skill_whiff_rate` 在此条件下不可信
- `skill_cast_rate` 仍然有效（基于 `skill_state.slot_states`）
