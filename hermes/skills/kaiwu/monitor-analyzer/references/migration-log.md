# 监控系统迁移记录

## v2 → v3 迁移（2026-05-29）

### 路径变更
- **旧**: `monitoring/fetch.py`, `monitoring/check.py`, `monitoring/plot.py`
- **新**: `.hermes/skills/kaiwu/monitor-analyzer/scripts/fetch.py` 等
- **旧 data**: `monitoring/data/`
- **新 data**: `.hermes/skills/kaiwu/monitor-analyzer/data/`

### 迁移步骤
1. `git pull origin dev` 拉取新代码
2. 复制 `config.local.yaml`（含 token + task_id）到新 skill 目录
3. `cp -r .hermes/skills/kaiwu/monitor-analyzer/* ~/.hermes/skills/kaiwu/monitor-analyzer/`
4. 验证：`cd scripts && python3 fetch.py --validate`
5. 更新 cron job 指向新脚本路径

### 新增能力（v3）
- `common.py` — 统一配置加载 + 统计量计算（含 cv 波动系数）
- `report.py` — 长期趋势 + 结构化诊断（severity 排序建议）
- `reference.md` — 指标解读框架 + 症状→动作决策表
- eval 指标组（评估胜率、对位胜率）
- skill 指标组（施放/命中/放空率）
- 按 task_id 分桶的 JSONL 历史记录
- fetch.py 结构化退出码（0=ok, 3=missing_config, 4=token_expired, 5=network, 6=api）
- check.py 配置化阈值（从 config.yaml 读取）

### 旧 skill 处理
- `kaiwu-monitor` — 已过时（指向 `monitoring/` 目录），应删除
- `arena-monitor` — API 参考内容已合并到 `monitor-analyzer/references/api-reference.md`

## URL 更新模式

用户给新 URL 时：
```bash
cd scripts
python3 fetch.py --update-config --url "https://tencentarena.com/p/v5/exp/monitor?..."
python3 fetch.py --validate
```

URL 变即新训练，history 自动开新桶（`data/history/<task_id>.jsonl`）。
