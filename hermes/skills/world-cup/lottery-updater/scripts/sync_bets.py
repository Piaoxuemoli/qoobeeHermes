#!/usr/bin/env python3
"""Sync bets from agents/*/round-N/bets.md to HTML AI_ROUNDS."""

import argparse
import json
import os
import re
import sys

AGENTS_DIR = os.path.expanduser("~/world-cup/agents")
HTML_FILE = os.path.expanduser("~/world-cup/世界杯预测.html")

MODEL_IDS = ["gpt55", "glm51", "qwen37", "deepseek", "mimo", "kimi"]


def parse_bets_md(filepath):
    """Parse a bets.md file and extract bet entries."""
    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    analysis = ""
    strategy = ""
    bets = []

    lines = content.split("\n")
    in_analysis = False
    in_table = False
    current_group = None
    group_guoguan = "2×1"
    group_amount = 0

    for line in lines:
        line = line.strip()

        if line.startswith("## 投注总览") or line.startswith("## 详细"):
            in_analysis = False

        if "analysis" in line.lower() or line.startswith("> "):
            in_analysis = True
            continue

        if line.startswith("###") and "组合" in line:
            match = re.search(r"(\d+)元", line)
            if match:
                group_amount = int(match.group(1))
            if "2×1" in line:
                group_guoguan = "2×1"
            elif "3×1" in line:
                group_guoguan = "3×1"
            elif "单关" in line:
                group_guoguan = "单关"
            continue

        if line.startswith("|") and "场次" in line:
            in_table = True
            continue

        if line.startswith("|") and in_table:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5 and cells[0] and not cells[0].startswith("-"):
                match_id = cells[0].strip()
                match_name = cells[1].strip()
                play_type = cells[2].strip()
                pick = cells[3].strip()
                odds_str = cells[4].strip().replace("@", "")
                try:
                    odds = float(odds_str)
                except ValueError:
                    odds = 0.0

                amount = group_amount if match_id.startswith("M") else 0
                bets.append({
                    "match": match_name,
                    "matchId": match_id,
                    "playType": play_type,
                    "pick": pick,
                    "amount": amount,
                    "odds": odds,
                    "过关": group_guoguan,
                    "actualScore": "",
                    "result": "pending",
                    "prize": 0,
                })
                group_amount = 0
            continue

        if in_table and not line.startswith("|"):
            in_table = False

    return {"analysis": analysis, "strategy": strategy, "bets": bets} if bets else None


def main():
    parser = argparse.ArgumentParser(description="Sync bets from agents to HTML")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    args = parser.parse_args()

    round_dir = f"round-{args.round}"
    predictions = {}

    for model_id in MODEL_IDS:
        bets_file = os.path.join(AGENTS_DIR, model_id, round_dir, "bets.md")
        parsed = parse_bets_md(bets_file)
        if parsed:
            predictions[model_id] = parsed
            print(f"Parsed {model_id}: {len(parsed['bets'])} bets", file=sys.stderr)

    if not predictions:
        print("No bets found for any model", file=sys.stderr)
        sys.exit(1)

    output = {"round": args.round, "predictions": predictions}
    out_file = os.path.expanduser(f"~/world-cup/.hermes/skills/world-cup/lottery-updater/data/round-{args.round}-bets.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Synced bets saved to {out_file}")


if __name__ == "__main__":
    main()
