#!/usr/bin/env python3
"""monitor-analyzer 公共工具。

被 fetch.py / plot.py / check.py / report.py 共用：
- 统一的配置加载与合并（修掉此前 fetch 与 check/plot 合并逻辑不一致的问题）
- API 返回数据的指标提取
- 统计量计算（含 std 与波动系数 cv，用于震荡判断）
- 按训练运行（task_id）分桶的长时段滚动摘要 history
"""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("错误: 需要 pyyaml 库。运行: pip install pyyaml")

# 目录结构：scripts/common.py -> skill 根目录
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SKILL_DIR / "config.yaml"
LOCAL_CONFIG_PATH = SKILL_DIR / "config.local.yaml"
DATA_DIR = SKILL_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
LATEST_PATH = DATA_DIR / "latest.json"
ALERT_PATH = DATA_DIR / "alert.json"


# ── 配置 ──

def load_config() -> dict:
    """加载配置：base(config.yaml) + local(config.local.yaml)，local 覆盖 base。

    统一合并逻辑，三脚本共用：
    - metric_groups 按组名浅合并（local 的组覆盖同名组，保留 base 其余组）
    - 其余键直接覆盖
    """
    cfg: dict = {}
    if CONFIG_PATH.exists():
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if LOCAL_CONFIG_PATH.exists():
        local = yaml.safe_load(LOCAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        for key, value in local.items():
            if key == "metric_groups" and isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key] = {**cfg[key], **value}
            else:
                cfg[key] = value
    return cfg


def save_local_config(cfg: dict) -> None:
    """写回 config.local.yaml（含 token 等敏感信息，已 gitignore）。"""
    LOCAL_CONFIG_PATH.write_text(
        yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ── API 数据提取 ──

def iter_metric_results(data: dict):
    """遍历 API results，yield (metric_name, items)。id 形如 name_3，去掉数字后缀。"""
    for result in data.get("data", {}).get("results", []):
        name = result.get("id", "").rsplit("_", 1)[0]
        yield name, result.get("items", [])


def extract_series(data: dict, metric_name: str):
    """返回指定指标的 (timestamps_ms, values)，按时间升序。找不到返回 ([], [])。"""
    for name, items in iter_metric_results(data):
        if name != metric_name:
            continue
        pairs = []
        for item in items:
            for point in item.get("values", []):
                val = point.get("value")
                ts = point.get("timestamp")
                if val is None or ts is None:
                    continue
                pairs.append((int(ts), float(val)))
        pairs.sort(key=lambda x: x[0])
        return [p[0] for p in pairs], [p[1] for p in pairs]
    return [], []


def metric_values(data: dict, metric_name: str) -> list:
    """返回指定指标的全部数值（不含时间戳）。"""
    _, values = extract_series(data, metric_name)
    return values


def available_metrics(data: dict) -> list:
    """返回 data 中实际有数据的指标名。"""
    return [name for name, items in iter_metric_results(data) if items]


# ── 统计 ──

def compute_stats(values) -> dict:
    """统计量：avg / min / max / std / cv / trend / trend_pct / n。

    - std: 总体标准差
    - cv : 波动系数 = std / |avg|，越大越震荡（供震荡判断与异常检测复用）
    - trend: 前 1/3 均值 vs 后 1/3 均值（↑ / ↓ / →）
    """
    if not values:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "std": 0.0, "cv": 0.0,
                "trend": "→", "trend_pct": 0.0, "n": 0}
    n = len(values)
    avg = sum(values) / n
    std = statistics.pstdev(values) if n > 1 else 0.0
    cv = (std / abs(avg)) if avg != 0 else 0.0
    third = max(1, n // 3)
    early = sum(values[:third]) / third
    late = sum(values[-third:]) / third
    pct = (late - early) / abs(early) * 100 if early != 0 else 0.0
    trend = "↑" if pct > 5 else ("↓" if pct < -5 else "→")
    return {"avg": round(avg, 4), "min": round(min(values), 4), "max": round(max(values), 4),
            "std": round(std, 4), "cv": round(cv, 3),
            "trend": trend, "trend_pct": round(pct, 1), "n": n}


def summarize_metrics(data: dict) -> dict:
    """对 data 内所有指标算 stats，返回 {name: stats}。"""
    summary = {}
    for name, items in iter_metric_results(data):
        if not items:
            continue
        values = []
        for item in items:
            for point in item.get("values", []):
                val = point.get("value")
                if val is not None:
                    values.append(float(val))
        summary[name] = compute_stats(values)
    return summary


# ── 长时段历史（按 task_id 分桶）──

def history_path(task_id) -> Path:
    return HISTORY_DIR / f"{task_id}.jsonl"


def append_history(task_id, record: dict) -> Path:
    """追加一条精简摘要到 data/history/<task_id>.jsonl。

    task_id 变（新 URL/新训练）会自动落到新文件，长期分析天然只在当前运行内。
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = history_path(task_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_history(task_id, since_hours: float | None = None) -> list:
    """读取当前 task_id 的历史摘要，可选只取最近 since_hours 小时。"""
    path = history_path(task_id)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if since_hours is not None and records:
        cutoff = datetime.now(timezone.utc).timestamp() - since_hours * 3600
        records = [r for r in records if _record_epoch(r) >= cutoff]
    return records


def _record_epoch(record: dict) -> float:
    ts = record.get("ts")
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return 0.0


def load_latest() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    return json.loads(LATEST_PATH.read_text(encoding="utf-8"))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
