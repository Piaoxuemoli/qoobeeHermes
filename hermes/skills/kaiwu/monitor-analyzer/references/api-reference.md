# 开悟平台 API 参考

API 逆向记录、端点清单、认证细节、指标全集。与 `arena-monitor` skill 合并而来。

## 认证机制

### Token
JWT token 从浏览器 cookie `kaiwu-token` 获取。Payload 包含 `custom`(user_id)、`exp`(7天)、`iss`("kaiwu")。

### x-kaiwu-auth 签名
```
x-kaiwu-ts: <Unix 时间戳(秒)>
x-kaiwu-auth: DJB2_HASH(timestamp + token[-32:] + endpoint)
```

DJB2 Python 实现：
```python
def kaiwu_auth(timestamp: int, token: str, endpoint: str) -> int:
    s = f"{timestamp}{token[-32:]}{endpoint}"
    r = 5381
    for c in s:
        r = r + (r << 5) + ord(c)
    return r & 0x7FFFFFFF
```

### 完整请求头
```
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>
Cookie: select_lang=zh; kaiwu-token=<token>
x-kaiwu-ts: <timestamp>
x-kaiwu-auth: <hash>
Referer: https://tencentarena.com/p/v5/exp/monitor
```

## API 端点

基础路径：`https://tencentarena.com/api/v5/Competition/`

- `GetTrainMetricRange` — 时间范围指标时序（**主用**）
- `GetTrainMetric` — 最新快照（可能返回空）
- `GetTrainLog` — 训练日志
- `GetTrainTask` — 任务详情
- `ListTrainTask` — 列出训练任务
- `ListTrainAiModel` — 列出训练模型
- `GetExperiment` — 实验信息

### 请求体结构（GetTrainMetricRange）
```json
{
  "domain": {"type": "competition_stage", "id": 444},
  "train_task_id": 187236,
  "competition_team_id": 7203,
  "experiment_id": 11425,
  "start_time": {"timestamp": "2026-05-28T16:00:00Z"},
  "end_time": {"timestamp": "2026-05-29T02:00:00Z"},
  "queries": [
    {"name": "win_rate", "expr": "round(avg(kaiwu_win_rate{model_id=\"selfplay\"}) by (model_id), 0.01)", "id": "win_rate_0", "step": "15"}
  ]
}
```

## 监控指标全集

### 基础指标
- `kaiwu_train_global_step` — 全局训练步数
- `kaiwu_actor_predict_succ_cnt` — Actor 预测成功数
- `kaiwu_sample_production_and_consumption_ratio` — 样本生产消费比
- `kaiwu_episode_cnt` — 对局数

### 环境指标
- `kaiwu_win_rate` — 胜率（selfplay）
- `kaiwu_self_tower_hp` / `kaiwu_enemy_tower_hp` — 塔血量
- `kaiwu_frame` — 对局帧数
- `kaiwu_kill` / `kaiwu_death` — 击杀/死亡
- `kaiwu_money_per_frame` — 每帧经济
- `kaiwu_hurt_to_hero` / `kaiwu_hurt_by_hero` — 每帧伤害

### 评估指标
- `kaiwu_eval_luban_win_rate` / `kaiwu_eval_direnjie_win_rate` — 评估胜率
- `kaiwu_luban_summoner_win_rate` / `kaiwu_direnjie_summoner_win_rate` — 召唤师胜率
- `kaiwu_direnjie_vs_luban_win_rate` / `kaiwu_luban_vs_direnjie_win_rate` — 对位胜率

### 算法损失
- `kaiwu_total_loss` / `kaiwu_policy_loss` / `kaiwu_entropy_loss`
- `kaiwu_value_loss_hp` / `kaiwu_value_loss_tower` / `kaiwu_value_loss_econ` / `kaiwu_value_loss_combat`

### 优化器
- `kaiwu_learning_rate` / `kaiwu_entropy_beta` / `kaiwu_grad_norm`

### 奖励分项
- `kaiwu_reward`（平台累积）/ `kaiwu_reward_sum`（对局总）
- `kaiwu_reward_hp` / `kaiwu_reward_tower` / `kaiwu_reward_econ` / `kaiwu_reward_combat`

### 技能使用（新增）
- `kaiwu_skill_cast_rate` — 每局施放次数
- `kaiwu_skill_hit_rate` — 命中数/施放数
- `kaiwu_skill_whiff_rate` — 放空数/施放数

### 对局质量
- `kaiwu_episode_frame` / `kaiwu_episode_win_value`

## Pitfalls

1. **x-kaiwu-auth 每次请求重新计算** — 不能缓存
2. **x-kaiwu-ts 必须是当前时间** — 过期返回 1401
3. **JWT 有效期 7 天** — 过期需用户重新登录
4. **PromQL 引号需要转义** — JSON 中 `model_id=\"selfplay\"`
5. **hash 函数可能版本变化** — 认证失败时检查 JS 源码
6. **SSR 数据不含实际指标值** — 只有 dashboard 配置
