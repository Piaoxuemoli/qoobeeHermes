#!/usr/bin/env python3
"""Fetch match results from ESPN/FIFA and output as JSON."""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta


def fetch_espn_results(date_str=None):
    """Fetch results from ESPN World Cup 2026 API.
    
    ⚠️ CORRECT ENDPOINT: /fifa.world/scoreboard?dates=YYYYMMDD
    The base /fifa.world endpoint returns 404!
    """
    if date_str is None:
        # Fetch today and yesterday in UTC to cover timezone differences
        utc_now = datetime.utcnow()
        dates = [
            utc_now.strftime("%Y%m%d"),
            (utc_now - timedelta(days=1)).strftime("%Y%m%d"),
        ]
    else:
        dates = [date_str]
    
    all_events = []
    for d in dates:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={d}"
        try:
            req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                all_events.extend(data.get("events", []))
        except Exception as e:
            print(f"Error fetching ESPN for {d}: {e}", file=sys.stderr)

    results = []
    seen = set()
    for event in all_events:
        event_name = event.get("name", "")
        if event_name in seen:
            continue
        seen.add(event_name)
        
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            continue
        
        # Extract scores from competitors (not scores array)
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
        
        home = away = ""
        home_score = away_score = "?"
        for c in competitors:
            team = c.get("team", {}).get("displayName", "")
            score = c.get("score", "?")
            if c.get("homeAway") == "home":
                home = team
                home_score = score
            else:
                away = team
                away_score = score
        
        results.append({
            "home": home,
            "away": away,
            "score": f"{home_score}:{away_score}",
            "status": "finished",
            "date": event.get("date", ""),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch World Cup 2026 match results")
    parser.add_argument("--round", type=int, help="Round number")
    parser.add_argument("--date", type=str, help="Specific date (YYYYMMDD)")
    parser.add_argument("--output", default="-", help="Output file (- for stdout)")
    parser.add_argument("--auto-update", action="store_true", help="Auto-update HTML if results found")
    args = parser.parse_args()

    results = fetch_espn_results(args.date)

    output = {"round": args.round, "results": results, "fetched_at": datetime.now().isoformat()}

    out_str = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(out_str)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_str)

    if args.auto_update and results:
        print(f"Found {len(results)} finished matches, running auto-update...", file=sys.stderr)


if __name__ == "__main__":
    main()
