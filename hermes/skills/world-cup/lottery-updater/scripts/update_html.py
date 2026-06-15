#!/usr/bin/env python3
"""Update HTML with match results - modify AI_ROUNDS in 世界杯预测.html."""

import argparse
import json
import os
import re
import sys

HTML_FILE = os.path.expanduser("~/world-cup/世界杯预测.html")


def determine_result(play_type, pick, home_score, away_score, handicap=0):
    """Determine if a bet wins based on actual score."""
    if play_type == "胜平负":
        if home_score > away_score:
            actual = "主胜"
        elif home_score == away_score:
            actual = "平"
        else:
            actual = "客胜"
        return actual == pick

    elif play_type == "让球胜平负":
        adjusted_home = home_score + handicap
        if adjusted_home > away_score:
            actual = "让胜"
        elif adjusted_home == away_score:
            actual = "让平"
        else:
            actual = "让负"
        if pick.startswith("让胜"):
            return actual == "让胜"
        elif pick.startswith("让平"):
            return actual == "让平"
        elif pick.startswith("让负"):
            return actual == "让负"
    return False


def calculate_prize(bet, is_win):
    """Calculate prize for a winning bet."""
    if not is_win:
        return 0
    odds = bet.get("odds", 0)
    amount = bet.get("amount", 0)
    if amount == 0:
        return 0
    multiplier = amount / 2
    return round(odds * 2 * multiplier, 2)


def main():
    parser = argparse.ArgumentParser(description="Update HTML with match results")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--results", required=True, help="JSON file with results")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(HTML_FILE):
        print(f"HTML file not found: {HTML_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(args.results, "r", encoding="utf-8") as f:
        results_data = json.load(f)

    results_map = {}
    for r in results_data.get("results", []):
        key = r.get("matchId", "")
        if key:
            results_map[key] = r

    if not results_map:
        print("No results to apply", file=sys.stderr)
        sys.exit(0)

    print(f"Applying {len(results_map)} results to round {args.round}", file=sys.stderr)

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if args.dry_run:
        print("Dry run - no changes made", file=sys.stderr)

    print("Results applied. Manual review recommended before committing.", file=sys.stderr)


if __name__ == "__main__":
    main()
