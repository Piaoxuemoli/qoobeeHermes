#!/usr/bin/env python3
"""长时段汇总 + 结构化诊断建议。

基于：
- data/latest.json   当前快照（各指标 stats）
- data/history/<task_id>.jsonl  当前训练运行的长期摘要

输出结构化 findings（status + 排序建议），供 monitor-analyzer skill 的
「结论与建议」段消费。决策规则与 reference.md 的「症状→动作」表对应。

用法:
    python3 report.py                 # 文本输出
    python3 report.py --json          # JSON 输出（供 skill 解析）
    python3 report.py --since 72h     # 长期趋势只看最近 72 小时
"""

import argparse
import json
import sys

import common

# 阈值
WHIFF_HIGH = 0.5            # 放空率高位
EVAL_WEAK = 0.45           # 评估胜率劣势线
TOWER_DOMINANCE = 2.0      # value_loss_tower / 其它头均值 倍数
OSC_CV = 0.8               # reward_sum / policy_loss 波动系数震荡线
WIN_FLAT_PCT = 1.0         # 胜率长期变化幅度（停滞）


def _avg(metrics, name):
    return metrics.get(name, {}).get("avg")


def _cv(metrics, name):
    return metrics.get(name, {}).get("cv")


def diagnose(metrics: dict) -> list:
    """对当前快照 metrics 做规则诊断，返回排序后的 findings。

    每个 finding: {severity: critical|warning|info, symptom, suggestion}
    """
    findings = []

    # 1) 多头价值不均衡：tower 头 value_loss 远大于其它头
    tower = _avg(metrics, "value_loss_tower")
    others = [_avg(metrics, n) for n in ("value_loss_hp", "value_loss_econ", "value_loss_combat")]
    others = [v for v in others if v is not None]
    if tower is not None and others:
        other_avg = sum(others) / len(others)
        if other_avg > 0 and tower / other_avg > TOWER_DOMINANCE:
            findings.append({
                "severity": "warning",
                "symptom": f"value_loss_tower({tower:.3f}) 是其它价值头均值({other_avg:.3f})的 {tower / other_avg:.1f}x",
                "suggestion": "多头价值尺度不均衡，tower 头主导共享 trunk 梯度。可在 compute_loss 给各头按目标尺度加系数，或下调 tower_hp_point 权重(当前6.0)。不破坏 checkpoint 加载。",
            })

    # 2) 技能乱放未收敛：放空率高位
    whiff = _avg(metrics, "skill_whiff_rate")
    if whiff is not None and whiff > WHIFF_HIGH:
        findings.append({
            "severity": "warning",
            "symptom": f"skill_whiff_rate={whiff:.2f} 高于 {WHIFF_HIGH}",
            "suggestion": "技能放空率偏高，乱放未收敛。可上调 SKILL_WHIFF_WEIGHT（当前-0.05）；注意 skill_cast_rate 不要被压到≈0。",
        })

    # 3) 评估/对位劣势
    for name, label in (("eval_luban_win_rate", "鲁班"), ("eval_direnjie_win_rate", "狄仁杰")):
        wr = _avg(metrics, name)
        if wr is not None and wr < EVAL_WEAK:
            findings.append({
                "severity": "warning",
                "symptom": f"{label}评估胜率 {wr:.2f} < {EVAL_WEAK}",
                "suggestion": f"{label}对 bot/对位处于劣势，结合对位胜率(vs)定位是哪类对手吃亏，针对性调奖励/课程。",
            })

    # 4) 震荡：reward_sum / policy_loss 波动系数过大
    for name, thr in (("reward_sum", OSC_CV), ("policy_loss", 1.0)):
        cv = _cv(metrics, name)
        if cv is not None and cv > thr:
            findings.append({
                "severity": "info",
                "symptom": f"{name} 波动系数 cv={cv:.2f} > {thr}",
                "suggestion": "短期波动偏大。先确认是否对称自对弈的固有抖动（看胜率而非 reward_sum）；若 policy_loss 持续高波动，考虑收回 clip-higher(CLIP_PARAM_HIGH 0.28→0.2)。",
            })

    # 5) 梯度爆炸
    grad = _avg(metrics, "grad_norm")
    if grad is not None and grad > 10:
        findings.append({
            "severity": "critical",
            "symptom": f"grad_norm={grad:.2f} 偏高(>10)",
            "suggestion": "梯度偏大，确认 GRAD_CLIP_RANGE(0.5) 是否生效；排查是否有奖励尖峰未被 clip。",
        })

    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return findings


def long_term_trend(history: list) -> dict:
    """对当前运行的长期 history 计算关键指标首末对比。"""
    if len(history) < 2:
        return {"points": len(history), "metrics": {}}
    first, last = history[0], history[-1]
    out = {}
    for name in ("reward_sum", "win_rate", "total_loss", "value_loss_tower",
                 "eval_luban_win_rate", "eval_direnjie_win_rate", "skill_whiff_rate"):
        a = first.get("metrics", {}).get(name, {}).get("avg")
        b = last.get("metrics", {}).get(name, {}).get("avg")
        if a is None or b is None:
            continue
        delta = b - a
        pct = (delta / abs(a) * 100) if a != 0 else 0.0
        out[name] = {"first": round(a, 4), "last": round(b, 4),
                     "delta": round(delta, 4), "pct": round(pct, 1)}
    return {
        "points": len(history),
        "train_step_first": first.get("train_step"),
        "train_step_last": last.get("train_step"),
        "metrics": out,
    }


def build_report(cfg: dict, since_hours: float | None) -> dict:
    task_id = cfg.get("task_id", "unknown")
    data = common.load_latest()
    snapshot = common.summarize_metrics(data) if data else {}
    history = common.read_history(task_id, since_hours=since_hours)
    findings = diagnose(snapshot)
    has_critical = any(f["severity"] == "critical" for f in findings)
    has_warning = any(f["severity"] == "warning" for f in findings)
    status = "异常" if has_critical else ("需关注" if has_warning else "正常")
    return {
        "stage": cfg.get("competition_stage", "未知"),
        "task_id": task_id,
        "status": status,
        "since_hours": since_hours,
        "long_term": long_term_trend(history),
        "findings": findings,
    }


def _parse_since(s: str | None) -> float | None:
    if not s:
        return None
    return float(str(s).rstrip("h"))


def main():
    parser = argparse.ArgumentParser(description="长时段汇总与诊断建议")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--since", help="长期趋势时间窗，如 72h")
    args = parser.parse_args()

    cfg = common.load_config()
    report = build_report(cfg, _parse_since(args.since))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"=== 训练诊断报告 ({report['stage']}, task_id={report['task_id']}) ===")
    print(f"状态: {report['status']}")
    lt = report["long_term"]
    print(f"\n长期趋势（{lt['points']} 个采样点, "
          f"train_step {lt.get('train_step_first')} → {lt.get('train_step_last')}）:")
    if lt["metrics"]:
        for name, d in lt["metrics"].items():
            print(f"  {name:24s} {d['first']:>9.4f} → {d['last']:>9.4f}  ({d['pct']:+.1f}%)")
    else:
        print("  (history 采样点不足，需多次 fetch 后才有长期趋势)")
    print("\n结论与建议:")
    if report["findings"]:
        for f in report["findings"]:
            print(f"  [{f['severity']}] {f['symptom']}\n      → {f['suggestion']}")
    else:
        print("  无显著异常，保持观察。")


if __name__ == "__main__":
    main()
