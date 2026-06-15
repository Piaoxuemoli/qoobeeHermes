#!/usr/bin/env python3
"""
批量更新 HTML 中 AI_ROUNDS bets 的模板脚本。
用法：修改 RESULTS 字典，运行脚本自动更新所有相关 bet 行。

关键模式：
- 用完整 bet 行字符串做 str.replace()，确保唯一匹配
- 同一 matchId 可能出现在多个模型中，需要分别处理
- amount=0 的腿是配腿，也需要更新 result 但不计算 prize
- 过关票 prize 只在主腿行（amount>0）计算，且需所有腿都有结果
"""

# === 需要更新的比赛结果 ===
RESULTS = {
    'M8': {'score': '0:1', 'result': '客胜'},   # 海地 0:1 苏格兰
    'M6': {'score': '2:0', 'result': '主胜'},   # 澳大利亚 2:0 土耳其
    'M9': {'score': '7:1', 'result': '主胜'},   # 德国 7:1 库拉索
    'M11': {'score': '2:2', 'result': '平'},    # 荷兰 2:2 日本
    'M10': {'score': '1:0', 'result': '主胜'},  # 科特迪瓦 1:0 厄瓜多尔
}

# === 每个 bet 的更新规则 ===
# 格式：(旧行完整字符串, 新行完整字符串)
# 注意：同一 pattern 可能出现在多个模型中，replace 会同时更新
UPDATES = [
    # M8 海地 vs 苏格兰 (0:1) - 客胜
    (
        "{ match: '海地 vs 苏格兰', matchId: 'M8', playType: '胜平负', pick: '客胜', amount: 0, odds: 1.31, 过关: '2×1', actualScore: '', result: 'pending', prize: 0 }",
        "{ match: '海地 vs 苏格兰', matchId: 'M8', playType: '胜平负', pick: '客胜', amount: 0, odds: 1.31, 过关: '2×1', actualScore: '0:1', result: 'win', prize: 0 }",
    ),
    # M9 德国 vs 库拉索 (7:1) - 让胜(-3) 单关
    (
        "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '让球胜平负', pick: '让胜(-3)', amount: 26, odds: 1.94, 过关: '单关', actualScore: '', result: 'pending', prize: 0 }",
        "{ match: '德国 vs 库拉索', matchId: 'M9', playType: '让球胜平负', pick: '让胜(-3)', amount: 26, odds: 1.94, 过关: '单关', actualScore: '7:1', result: 'win', prize: 50.44 }",
    ),
    # 过关票奖金更新（所有腿都完成后）
    (
        "{ match: '美国 vs 巴拉圭', matchId: 'M5', playType: '胜平负', pick: '主胜', amount: 56, odds: 1.40, 过关: '2×1', actualScore: '4:1', result: 'win', prize: 0 }",
        "{ match: '美国 vs 巴拉圭', matchId: 'M5', playType: '胜平负', pick: '主胜', amount: 56, odds: 1.40, 过关: '2×1', actualScore: '4:1', result: 'win', prize: 137.20 }",
    ),
]

HTML_PATH = '/root/world-cup/世界杯预测.html'

def main():
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = []
    for old, new in UPDATES:
        count = content.count(old)
        if count == 0:
            print(f"  WARN: pattern not found: {old[:80]}...")
            continue
        content = content.replace(old, new)
        changes.append(f"  OK ({count}x): {old[:60]}...")

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    for c in changes:
        print(c)
    print(f"\nTotal: {len(changes)} replacements applied")

if __name__ == '__main__':
    main()
