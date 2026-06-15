---
name: kaiwu-monitor
description: "Use when working with the Kaiwu platform monitoring system — fetching training metrics, plotting charts, running anomaly checks, or updating monitor config. Covers the monitoring/ directory: fetch.py, check.py, plot.py, config.yaml."
version: 1.0.0
author: Qoobee
platforms: [linux]
metadata:
  hermes:
    tags: [kaiwu, monitoring, rl, training]
    related_skills: [rl-advisor, repo-scanner]
---

# Kaiwu Monitor

开悟平台训练监控系统。自动抓取训练指标、绘图、异常检测。

## When to Use

- 用户问"看看训练状态"、"reward 怎么样"
- 需要抓取训练监控数据
- 需要生成训练图表
- 需要检查训练异常
- 需要更新监控配置（token、task_id 等）

Don't use for: 代码修改（用 git 工作流）、RL 理论问题（用 rl-advisor）

## 文件结构

```
monitoring/
├── config.yaml           # 模板配置（提交 git）
├── config.local.yaml     # 真实配置（不提交，.gitignore）
├── fetch.py              # 数据抓取（DJB2 auth + API 调用）
├── check.py              # 异常检测（cron 调用）
├── plot.py               # 绘图（matplotlib Agg backend）
└── data/
    ├── latest.json       # 最新快照
    └── YYYY-MM-DD.json   # 每天归档
```

## 快速命令

```bash
cd /root/Kaiwu_2026

# 验证连接
python3 monitoring/fetch.py --validate

# 抓取数据
python3 monitoring/fetch.py --hours 6
python3 monitoring/fetch.py --hours 1 --groups quick_check

# 异常检测
python3 monitoring/check.py

# 绘图
python3 monitoring/plot.py
python3 monitoring/plot.py --hours 12

# 更新配置
python3 monitoring/fetch.py --update-config --token NEW_TOKEN
python3 monitoring/fetch.py --update-config --url "https://tencentarena.com/...task_id=183628&..."
```

## 认证机制

Kaiwu 平台 API 使用自定义认证：

```
Authorization: Bearer <token>
Cookie: select_lang=zh; kaiwu-token=<token>
x-kaiwu-ts: <当前Unix时间戳(秒)>
x-kaiwu-auth: <DJB2_HASH(ts + token[-32:] + endpoint)>
```

**DJB2 算法**（从 JS 源码逆向）：
```python
def kaiwu_auth(timestamp: int, token: str, endpoint: str) -> int:
    s = f"{timestamp}{token[-32:]}{endpoint}"
    r = 5381
    for c in s:
        r = r + (r << 5) + ord(c)
    return r & 0x7FFFFFFF
```

完整逆向过程记录：`docs/sop/开悟平台监控API接入SOP.md`

## API 端点

| 端点 | 用途 |
|------|------|
| `GetTrainMetricRange` | 时间范围内的指标时序数据（推荐） |
| `GetTrainMetric` | 最新快照（可能返回空） |
| `GetTrainLog` | 训练日志 |
| `GetTrainTask` | 任务详情 |

## 配置管理

`config.local.yaml` 覆盖 `config.yaml` 的字段。`load_config()` 函数合并两个文件：
- base (`config.yaml`) 提供 metric_groups 等默认值
- local (`config.local.yaml`) 提供 token、task_id 等敏感字段

**⚠️ 坑点**：三个脚本的 `load_config` 必须都实现合并逻辑，否则会丢失 metric_groups。

## 用户修改分支

### token 更新
```
用户: "token 过期了，新的 token 是 xxx"
→ python3 monitoring/fetch.py --update-config --token xxx
→ python3 monitoring/fetch.py --validate
→ "已更新 ✓"
```

### 新训练启动
```
用户: "新训练 URL 是 https://tencentarena.com/...task_id=183628&..."
→ 从 URL 解析参数
→ python3 monitoring/fetch.py --update-config --url URL
→ "已切换 ✓"
```

### 赛段切换
```
用户: "现在打全国决赛了"
→ python3 monitoring/fetch.py --update-config --stage 全国决赛
→ "已切换，请提供新 URL"
```

## 常见问题

### 1. 返回空数据
- 检查时间范围是否正确
- 用 `GetTrainMetricRange` 而不是 `GetTrainMetric`

### 2. 中文字体显示为方块
```bash
# 安装中文字体
dnf install -y google-noto-sans-cjk-sc-fonts  # RHEL/CentOS
apt install -y fonts-noto-cjk                  # Debian/Ubuntu

# 清除 matplotlib 缓存
rm -rf ~/.cache/matplotlib

# plot.py 中配置
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
```

### 3. config.local.yaml 不生效
检查 `load_config()` 是否实现了 base + local 合并逻辑。

## 指标分组（按分析场景）

```yaml
metric_groups:
  quick_check: [win_rate, reward, total_loss, train_step]
  reward_analysis: [reward_sum, reward_hp, reward_tower, reward_econ, reward_combat]
  loss_analysis: [value_loss_hp, value_loss_tower, value_loss_econ, value_loss_combat, policy_loss, entropy_loss]
  convergence: [episode_win_value, grad_norm, entropy_beta]
  environment: [self_tower_hp, enemy_tower_hp, kill, death, frame]
```
