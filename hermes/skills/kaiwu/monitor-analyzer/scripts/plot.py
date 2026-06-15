#!/usr/bin/env python3
"""训练监控数据绘图工具。

用法:
    python3 plot.py                    # 绘制所有可用图（最近 6 小时快照）
    python3 plot.py --hours 12         # 时间范围标注用
    python3 plot.py --groups reward_analysis eval_analysis  # 指定组
    python3 plot.py --output /tmp/charts  # 指定输出目录

输出图：
    reward_trend.png / loss_curve.png / convergence.png / environment.png
    eval.png        — 评估与对位胜率
    skill.png       — 技能施放/命中/放空率
    longterm.png    — 当前训练运行的长期趋势（按 train_step，读 history）
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")  # 无头渲染，必须在 import pyplot 之前
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
except ImportError:
    print("错误: 需要 matplotlib 库。运行: pip install matplotlib")
    sys.exit(1)

import common

COLORS = {
    "reward_sum": "#2ecc71", "reward_hp": "#27ae60", "reward_tower": "#16a085",
    "reward_econ": "#2980b9", "reward_combat": "#e74c3c",
    "total_loss": "#e74c3c", "policy_loss": "#3498db", "entropy_loss": "#9b59b6",
    "value_loss_hp": "#e67e22", "value_loss_tower": "#d35400",
    "value_loss_econ": "#f39c12", "value_loss_combat": "#c0392b",
    "win_rate": "#2ecc71", "episode_win_value": "#1abc9c",
    "grad_norm": "#8e44ad", "entropy_beta": "#34495e", "train_step": "#7f8c8d",
    "self_tower_hp": "#2ecc71", "enemy_tower_hp": "#e74c3c",
    "kill": "#27ae60", "death": "#c0392b", "frame": "#95a5a6",
    "eval_luban_win_rate": "#2ecc71", "eval_direnjie_win_rate": "#16a085",
    "luban_summoner_win_rate": "#27ae60", "direnjie_summoner_win_rate": "#1abc9c",
    "direnjie_vs_luban_win_rate": "#e67e22", "luban_vs_direnjie_win_rate": "#d35400",
    "skill_cast_rate": "#3498db", "skill_hit_rate": "#2ecc71", "skill_whiff_rate": "#e74c3c",
}
DEFAULT_COLOR = "#3498db"

# 指标组 -> (输出文件名, 图标题)
GROUP_CHARTS = {
    "reward_analysis": ("reward_trend.png", "Reward 趋势"),
    "loss_analysis": ("loss_curve.png", "Loss 曲线"),
    "convergence": ("convergence.png", "收敛指标"),
    "environment": ("environment.png", "环境指标"),
    "eval_analysis": ("eval.png", "评估与对位胜率"),
    "skill_usage": ("skill.png", "技能使用（施放/命中/放空）"),
}


def plot_metric_group(data, metrics, title, output_path) -> bool:
    fig, ax = plt.subplots(figsize=(12, 5))
    plotted = 0
    for m in metrics:
        name = m["name"]
        ts_ms, values = common.extract_series(data, name)
        if not ts_ms:
            continue
        timestamps = [datetime.fromtimestamp(t / 1000) for t in ts_ms]
        ax.plot(timestamps, values, label=name, color=COLORS.get(name, DEFAULT_COLOR),
                linewidth=1.5, alpha=0.85)
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return False
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("时间")
    ax.set_ylabel("值")
    ax.legend(loc="upper left", fontsize=9, ncol=min(3, plotted))
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def plot_longterm(cfg, output_dir) -> Path | None:
    """读当前 task_id 的 history，绘制关键指标随 train_step 的长期趋势。"""
    task_id = cfg.get("task_id", "unknown")
    history = common.read_history(task_id)
    if len(history) < 2:
        return None
    key_metrics = ["reward_sum", "win_rate", "total_loss", "value_loss_tower"]
    xs = [r.get("train_step") or i for i, r in enumerate(history)]
    fig, ax = plt.subplots(figsize=(12, 5))
    plotted = 0
    for name in key_metrics:
        ys = [r.get("metrics", {}).get(name, {}).get("avg") for r in history]
        pairs = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if len(pairs) < 2:
            continue
        px, py = zip(*pairs)
        ax.plot(px, py, label=name, color=COLORS.get(name, DEFAULT_COLOR),
                marker="o", markersize=3, linewidth=1.5, alpha=0.85)
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return None
    ax.set_title(f"长期趋势 (task_id={task_id}, {len(history)} 个采样点)", fontsize=14, fontweight="bold")
    ax.set_xlabel("train_step")
    ax.set_ylabel("值")
    ax.legend(loc="upper left", fontsize=9, ncol=min(4, plotted))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = output_dir / "longterm.png"
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description="训练监控绘图")
    parser.add_argument("--hours", type=float, default=6, help="时间范围（小时，仅标注用）")
    parser.add_argument("--groups", nargs="*", help="指定指标组")
    parser.add_argument("--output", type=str, help="输出目录")
    args = parser.parse_args()

    cfg = common.load_config()
    data = common.load_latest()
    if data is None:
        print("无监控数据，请先运行 fetch.py")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else Path(
        cfg.get("plot", {}).get("output_dir", "/tmp/monitor_charts"))
    output_dir.mkdir(parents=True, exist_ok=True)

    target_groups = args.groups or list(GROUP_CHARTS.keys())
    generated = []
    for group_name in target_groups:
        if group_name not in GROUP_CHARTS:
            continue
        filename, title = GROUP_CHARTS[group_name]
        metrics = cfg.get("metric_groups", {}).get(group_name, [])
        if metrics and plot_metric_group(data, metrics, title, output_dir / filename):
            generated.append(str(output_dir / filename))
            print(f"✓ 已生成: {output_dir / filename}")
        else:
            print(f"✗ {group_name}: 无数据")

    # 长期趋势（读 history，与 groups 无关）
    if not args.groups or "longterm" in args.groups:
        lt = plot_longterm(cfg, output_dir)
        if lt:
            generated.append(str(lt))
            print(f"✓ 已生成: {lt}")
        else:
            print("✗ longterm: history 采样点不足（<2）")

    if not generated:
        print("未生成任何图表（数据可能为空）")
        sys.exit(1)
    print(f"\n图表已保存到: {output_dir}（共 {len(generated)} 张）")


if __name__ == "__main__":
    main()
