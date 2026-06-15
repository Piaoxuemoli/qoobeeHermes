# Batch Update HTML Bets

When a single match result affects many bets across multiple models (e.g., M5 appears in 36 bets),
use a Python script to batch-update instead of calling `patch()` 36 times.

## 方法一：正则匹配（通用，自动判定）

```python
#!/usr/bin/env python3
"""Batch update match results via regex — auto-determines win/loss from pick."""
import re

HTML_PATH = '/root/world-cup/世界杯预测.html'

def update_match(match_id, actual_score, result_logic):
    """
    match_id: e.g. 'M5'
    actual_score: e.g. '4:1'
    result_logic: function(pick, play_type) -> 'win'|'loss'
    """
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    updated = []
    for line in lines:
        if f"matchId: '{match_id}'" in line:
            line = re.sub(r"actualScore: ''", f"actualScore: '{actual_score}'", line)
            if "result: 'pending'" in line:
                pick_match = re.search(r"pick: '([^']*)'", line)
                play_match = re.search(r"playType: '([^']*)'", line)
                if pick_match and play_match:
                    result = result_logic(pick_match.group(1), play_match.group(1))
                    line = re.sub(r"result: 'pending'", f"result: '{result}'", line)
        updated.append(line)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(updated))
```

**⚠️ 注意**：正则方式会匹配所有包含该 matchId 的行，包括 amount 不同的同名比赛。
如果同一比赛名出现在不同赔率/金额的 bet 中（如 gpt55 和 kimi 都投注了 M8），需额外检查 amount/odds。

## 方法二：完整行字符串替换（推荐，精确匹配）

用完整 bet 行字符串做 `str.replace()`，确保唯一匹配。同一 matchId 可能出现多次（不同 amount/odds/pick/playType），必须用完整行匹配。

```python
#!/usr/bin/env python3
"""Batch update via exact string matching — more reliable than regex."""
HTML_PATH = '/root/world-cup/世界杯预测.html'

UPDATES = [
    # (旧行, 新行) — 必须包含足够字段确保唯一
    (
        "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '让球胜平负', pick: '让胜(-3)', amount: 26, odds: 1.94, 过关: '单关', actualScore: '', result: 'pending', prize: 0 }",
        "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '让球胜平负', pick: '让胜(-3)', amount: 26, odds: 1.94, 过关: '单关', actualScore: '7:1', result: 'win', prize: 50.44 }",
    ),
]

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()
for old, new in UPDATES:
    n = content.count(old)
    if n > 0:
        content = content.replace(old, new)
        print(f"Replaced {n}x: {old[:80]}...")
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
```

**优点**：不会误匹配同名不同赔率的 bet；支持同时更新 prize。

## Key Points

1. **只更新 `result: 'pending'`** — 避免覆盖已结算的投注
2. **过关票的 amount=0 腿** — 这些是配腿，不单独计算奖金，但 result 仍需更新
3. **让球胜平负** — 必须手动计算让球后比分再判定
4. **过关票 prize** — 只在主腿行（amount>0）更新 prize，且需所有腿都有结果
5. **更新后必须 cp + docker cp + caddy reload** — 否则页面不会刷新

## ESPN API 日期映射（北京时间 → UTC → API 参数）

| 北京时间窗口 | UTC 范围 | 需拉取的 API dates |
|-------------|----------|-------------------|
| 6/14 09:00 ~ 6/15 09:00 | 6/13 01:00 ~ 6/14 01:00 UTC | 20260613, 20260614, 20260615 |
| 6/15 09:00 ~ 6/16 09:00 | 6/14 01:00 ~ 6/15 01:00 UTC | 20260614, 20260615, 20260616 |

规则：拉取 **窗口前一天UTC + 窗口当天UTC + 窗口后一天UTC** 三天数据，确保不遗漏。
原因：UTC 日期分组的比赛可能在次日凌晨（北京时间）才结束。
