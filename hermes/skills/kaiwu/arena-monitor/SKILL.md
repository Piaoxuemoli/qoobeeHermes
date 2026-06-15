---
name: arena-monitor
description: Scrape training metrics from Tencent AI Arena (tencentarena.com) monitoring dashboard. Covers JWT auth, x-kaiwu-auth signature, API endpoints, and metric extraction.
version: 1.0.0
author: QoobeeHermes
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, monitoring, api, metrics]
    related_skills: [rl-advisor, repo-sync]
---

# Arena Monitor

从腾讯开悟平台 (tencentarena.com) 抓取训练监控数据。

## 认证机制

### Token

JWT token 从浏览器 cookie `kaiwu-token` 获取，同时作为 `Authorization: Bearer` 头。

JWT payload 包含：
- `custom`: user_id（如 15850）
- `exp`: 过期时间（通常 7 天）
- `iss`: "kaiwu"

### x-kaiwu-auth 签名

每个 API 请求需要两个自定义头：

```
x-kaiwu-ts: <当前 Unix 时间戳（秒）>
x-kaiwu-auth: DJB2_HASH(timestamp + token_last_32_chars + url_last_path_segment)
```

DJB2 hash 实现（JavaScript 源码）：
```javascript
function k9(t) {
    return function(t, e) {
        for (var r = 5381, n = 0, o = e.length; n < o; ++n)
            r += (r << 5) + e.charCodeAt(n);
        return 2147483647 & r
    }(0, t)
}
```

Python 实现：
```python
def kaiwu_auth_hash(timestamp: int, token: str, url_path: str) -> int:
    last32 = token[-32:]
    last_segment = url_path.rstrip('/').split('/')[-1]
    data = f"{timestamp}{last32}{last_segment}"
    r = 5381
    for c in data:
        r = (r + (r << 5) + ord(c)) & 0xFFFFFFFF
    return r & 2147483647
```

### 完整请求头

```
Cookie: select_lang=zh; kaiwu-token=<JWT>
Authorization: Bearer <JWT>
x-kaiwu-auth: <hash>
x-kaiwu-ts: <timestamp>
Referer: https://tencentarena.com/p/v5/exp/monitor
```

## API 端点

基础路径：`https://tencentarena.com/api/v5/Competition/`

| 端点 | 方法 | 说明 |
|------|------|------|
| `GetTrainTask` | POST | 获取训练任务信息 |
| `GetTrainLog` | POST | 获取训练日志 |
| `GetTrainMetric` | POST | 获取指标数据（PromQL 查询） |
| `GetTrainMetricRange` | POST | 获取指标时间范围 |
| `ListTrainTask` | POST | 列出训练任务 |
| `ListTrainAiModel` | POST | 列出训练模型 |
| `GetExperiment` | POST | 获取实验信息 |

### 请求体结构

```json
{
  "domain": {"type": "competition_stage", "id": 444},
  "train_task_id": 183628,
  "competition_team_id": 7203,
  "experiment_id": 11425,
  "start_time": {"timestamp": "2026-05-27T16:00:00Z"},
  "end_time": {"timestamp": "2026-05-28T02:00:00Z"},
  "queries": [
    {"expr": "round(avg(kaiwu_win_rate{model_id=\"selfplay\"}) by (model_id), 0.01)"}
  ]
}
```

## 监控指标

### 基础指标（6 项）
- `kaiwu_train_global_step` — 全局训练步数
- `kaiwu_actor_predict_succ_cnt` — Actor 预测成功数
- `kaiwu_sample_production_and_consumption_ratio` — 样本生产消费比
- `kaiwu_episode_cnt` — 对局数
- `kaiwu_actor_load_last_model_succ_cnt` — Actor 加载最新模型成功数
- `kaiwu_sample_receive_cnt` — 样本接收数

### 环境指标（6 项）
- `kaiwu_win_rate` — 胜率（selfplay 对局）
- `kaiwu_self_tower_hp` / `kaiwu_enemy_tower_hp` — 塔血量
- `kaiwu_frame` — 对局帧数
- `kaiwu_kill` / `kaiwu_death` — 击杀/死亡数
- `kaiwu_money_per_frame` — 每帧经济
- `kaiwu_hurt_to_hero` / `kaiwu_hurt_by_hero` — 每帧伤害

### 评估指标（6 项）
- 跨英雄胜率：`kaiwu_direnjie_vs_luban_win_rate`、`kaiwu_luban_vs_direnjie_win_rate`
- 评估英雄胜率：`kaiwu_eval_luban_win_rate`、`kaiwu_eval_direnjie_win_rate`
- 英雄召唤师胜率：`kaiwu_luban_summoner_win_rate`、`kaiwu_direnjie_summoner_win_rate`

### 算法损失（5 项）
- `kaiwu_total_loss`、`kaiwu_value_loss`、`kaiwu_policy_loss`、`kaiwu_entropy_loss`
- Value loss 分项：`kaiwu_value_loss_hp`、`kaiwu_value_loss_tower`、`kaiwu_value_loss_econ`、`kaiwu_value_loss_combat`

### 优化器状态（3 项）
- `kaiwu_learning_rate`、`kaiwu_entropy_beta`、`kaiwu_grad_norm`

### 训练吞吐（2 项）
- `kaiwu_sample_batch_size`、`kaiwu_train_step`

### 奖励指标（3 项）
- `kaiwu_reward`（平台累积回报）、`kaiwu_reward_sum`（对局总回报）
- 奖励分项：`kaiwu_reward_hp`、`kaiwu_reward_tower`、`kaiwu_reward_econ`、`kaiwu_reward_combat`

### 对局质量（2 项）
- `kaiwu_episode_frame`、`kaiwu_episode_win_value`

## SSR 数据提取

监控页面是 Next.js RSC (React Server Components) 应用。页面 HTML 中嵌入了：
- 任务信息（status, algorithm, training_mode, version）
- Dashboard 配置（指标名 + PromQL 表达式）
- React Query state（task data, time range）

提取方法：用 curl 带认证头请求页面 URL，然后从 `self.__next_f.push([1, "..."])` payload 中解析 JSON。

## 已知参数（当前任务）

| 参数 | 值 |
|------|------|
| task_id | 189696 |
| task_uuid | 57738cce-5bfb-4183-8ab2-37b57bb407cb |
| team_id | 7203 |
| domain_id | 444 |
| exp_id | 11425 |
| algorithm | PPO |
| training_mode | Distributed |
| status | running |

## Pitfalls

1. **x-kaiwu-auth 不是固定值** — 每次请求需要用当前时间戳重新计算
2. **x-kaiwu-ts 必须是当前时间** — 过期的 timestamp 会返回 1401 非法请求
3. **JWT 有效期 7 天** — 过期后需要用户重新登录获取新 token
4. **SSR 数据不含实际指标值** — 只有 dashboard 配置，实际数据需要客户端 API 请求
5. **PromQL 表达式中的引号需要转义** — JSON 中 `model_id=\"selfplay\"` 需要反斜杠转义
6. **hash 函数可能因版本更新变化** — 如果认证失败，重新检查 JS chunk 中的 k9 实现
