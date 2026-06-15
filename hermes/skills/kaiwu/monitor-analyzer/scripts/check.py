#!/usr/bin/env python3
"""训练异常检测（cron 调用）。

每 30 分钟运行一次，检查 data/latest.json 是否满足 failure_conditions。
检测到异常时写入 data/alert.json 供 monitor-analyzer skill 读取。

支持的检测类型（condition 关键字）：
- drop > N%      : window 内均值下降超过 N%
- spike > Nx     : 当前值是近期均值的 N 倍以上
- flat > Nh      : window 内变化 < 1%（训练卡住）
- high > V       : 近期均值高于阈值 V（如放空率维持高位）
- oscillate > C  : window 内波动系数 cv(std/|avg|) 高于 C（震荡）

用法:
    python3 check.py              # 检测并输出结果
    python3 check.py --json       # JSON 输出（供程序读取）
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import common


def _window_points(values: list, window_minutes: float) -> list:
    """取最近 window_minutes 分钟内的 (ts, value) 点。"""
    if not values:
        return []
    now = values[-1][0]
    window_ms = window_minutes * 60 * 1000
    return [(ts, v) for ts, v in values if now - ts <= window_ms]


def check_drop(values, threshold_pct, window_minutes):
    pts = _window_points(values, window_minutes)
    if len(pts) < 5:
        return None
    third = max(1, len(pts) // 3)
    early = sum(v for _, v in pts[:third]) / third
    late = sum(v for _, v in pts[-third:]) / third
    if early == 0:
        return None
    drop_pct = (early - late) / abs(early) * 100
    if drop_pct > threshold_pct:
        return {"type": "drop", "detail": f"下降 {drop_pct:.0f}%（{early:.3f} → {late:.3f}）",
                "window": f"{window_minutes / 60:.0f}h"}
    return None


def check_spike(values, threshold_x):
    if len(values) < 20:
        return None
    recent = [v for _, v in values[-20:]]
    recent_avg = sum(recent) / len(recent)
    current = values[-1][1]
    if recent_avg == 0:
        return None
    ratio = current / recent_avg
    if ratio > threshold_x:
        return {"type": "spike", "detail": f"当前值 {current:.3f} 是近期均值 {recent_avg:.3f} 的 {ratio:.1f}x"}
    return None


def check_flat(values, window_hours):
    pts = _window_points(values, window_hours * 60)
    if len(pts) < 5:
        return None
    vals = [v for _, v in pts]
    avg = sum(vals) / len(vals)
    if avg == 0:
        return None
    variation = (max(vals) - min(vals)) / abs(avg) * 100
    if variation < 1:
        return {"type": "flat", "detail": f"最近 {window_hours:.0f}h 变化仅 {variation:.2f}%（可能训练卡住）",
                "window": f"{window_hours:.0f}h"}
    return None


def check_high(values, threshold):
    if len(values) < 10:
        return None
    recent = [v for _, v in values[-10:]]
    avg = sum(recent) / len(recent)
    if avg > threshold:
        return {"type": "high", "detail": f"近期均值 {avg:.3f} 高于阈值 {threshold:.3f}"}
    return None


def check_oscillate(values, threshold_cv, window_minutes):
    pts = _window_points(values, window_minutes)
    if len(pts) < 10:
        return None
    stats = common.compute_stats([v for _, v in pts])
    if stats["cv"] > threshold_cv:
        return {"type": "oscillate", "detail": f"最近 {window_minutes / 60:.0f}h 波动系数 cv={stats['cv']:.2f} > {threshold_cv}（震荡偏大）",
                "window": f"{window_minutes / 60:.0f}h"}
    return None


def _parse_threshold(condition: str) -> float:
    """从 'drop > 50%' / 'spike > 10x' / 'high > 0.5' 中取数值。"""
    raw = condition.split(">")[1].strip()
    return float(raw.rstrip("%xh"))


def _parse_window_minutes(cond: dict, default_hours: float) -> float:
    window = str(cond.get("window", f"{default_hours}h")).rstrip("h")
    return float(window) * 60


def run_checks(cfg: dict, data: dict) -> list:
    conditions = cfg.get("auto_trigger", {}).get("failure_conditions", [])
    alerts = []
    for cond in conditions:
        metric = cond["metric"]
        condition = cond["condition"]
        # extract_series 返回 (timestamps, values)，转成 [(ts, v), ...]
        ts, vals = common.extract_series(data, metric)
        points = list(zip(ts, vals))
        if not points:
            continue

        if "drop" in condition:
            result = check_drop(points, _parse_threshold(condition), _parse_window_minutes(cond, 1))
        elif "spike" in condition:
            result = check_spike(points, _parse_threshold(condition))
        elif "flat" in condition:
            result = check_flat(points, _parse_window_minutes(cond, 4) / 60)
        elif "high" in condition:
            result = check_high(points, _parse_threshold(condition))
        elif "oscillate" in condition:
            result = check_oscillate(points, _parse_threshold(condition), _parse_window_minutes(cond, 2))
        else:
            continue

        if result:
            result["metric"] = metric
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            alerts.append(result)
    return alerts


def main():
    parser = argparse.ArgumentParser(description="训练异常检测")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    cfg = common.load_config()
    if not cfg.get("auto_trigger", {}).get("enabled", False):
        print(json.dumps({"status": "disabled"}) if args.json else "异常检测已禁用")
        return

    data = common.load_latest()
    if data is None:
        msg = {"status": "no_data", "message": "无监控数据，请先运行 fetch.py"}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg["message"])
        sys.exit(1)

    alerts = run_checks(cfg, data)
    result = {
        "status": "alert" if alerts else "ok",
        "check_time": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
    }

    if alerts:
        common.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(common.ALERT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        if not args.json:
            print(f"⚠️ 检测到 {len(alerts)} 个异常:")
            for a in alerts:
                print(f"  - [{a['metric']}] {a['type']}: {a['detail']}")
            print(f"告警已写入 {common.ALERT_PATH}")
    else:
        if common.ALERT_PATH.exists():
            common.ALERT_PATH.unlink()
        if not args.json:
            print("✓ 无异常")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
