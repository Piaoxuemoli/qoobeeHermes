#!/usr/bin/env python3
"""开悟平台训练监控数据抓取工具。

用法:
    python3 fetch.py --validate                  # 验证 token 和连接
    python3 fetch.py --hours 6                   # 抓取最近 6 小时数据
    python3 fetch.py --hours 1 --groups quick_check  # 只抓 quick_check 指标
    python3 fetch.py --update-config --token NEW_TOKEN  # 更新配置
    python3 fetch.py --update-config --url "https://tencentarena.com/..."  # 从 URL 解析参数

抓取成功后自动：
- 写 data/latest.json（供 plot/check/report 读取）
- 追加一条精简摘要到 data/history/<task_id>.jsonl（长时段记录，按训练运行分桶）
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("错误: 需要 requests 库。运行: pip install requests")
    sys.exit(1)

import common

API_BASE = "https://tencentarena.com/api/v5/Competition"
ENDPOINTS = {
    "range": "GetTrainMetricRange",
    "metric": "GetTrainMetric",
    "log": "GetTrainLog",
    "task": "GetTrainTask",
}

# 抓取所必需的配置字段（缺任一则无法请求）。task_uuid 当前未参与请求体，不强制。
REQUIRED_FIELDS = ["token", "task_id", "team_id", "domain_id", "exp_id"]

# 状态 -> (exit_code, 需要用户提供, 友好提示)。供 Hermes 按 status/exit_code 分支。
STATUS_INFO = {
    "ok":             (0, [],        "连接正常，token 有效"),
    "missing_config": (3, ["url"],   "配置缺失：需要监控页面 URL（含 task_id/team_id/domain_id/exp_id）"),
    "token_expired":  (4, ["token"], "token 已过期：需要新的 kaiwu-token（浏览器 cookie kaiwu-token）"),
    "network_error":  (5, [],        "网络错误：无法连接开悟平台，请检查网络后重试"),
    "api_error":      (6, [],        "API 返回错误"),
}


def kaiwu_auth(timestamp: int, token: str, endpoint: str) -> int:
    """DJB2 hash: x-kaiwu-auth 计算。"""
    s = f"{timestamp}{token[-32:]}{endpoint}"
    r = 5381
    for c in s:
        r = r + (r << 5) + ord(c)
    return r & 0x7FFFFFFF


def build_headers(token: str, endpoint: str) -> dict:
    """构建请求 headers（含 DJB2 签名）。"""
    ts = str(int(time.time()))
    auth = kaiwu_auth(int(ts), token, endpoint)
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Cookie": f"select_lang=zh; kaiwu-token={token}",
        "x-kaiwu-ts": ts,
        "x-kaiwu-auth": str(auth),
        "Referer": "https://tencentarena.com/p/v5/exp/monitor",
    }


def build_queries(cfg: dict, groups: list | None = None) -> list:
    """从配置构建 queries 列表。"""
    all_metrics = cfg.get("metric_groups", {})
    queries = []
    idx = 0
    target_groups = groups or list(all_metrics.keys())
    for group_name in target_groups:
        for m in all_metrics.get(group_name, []):
            queries.append({
                "name": m["name"],
                "expr": m["expr"],
                "id": f"{m['name']}_{idx}",
                "step": "15",
            })
            idx += 1
    return queries


def fetch_range(cfg: dict, hours: float = 6, groups: list | None = None) -> dict:
    """调用 GetTrainMetricRange 获取时序数据。"""
    token = cfg["token"]
    endpoint = ENDPOINTS["range"]
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    body = {
        "domain": {"type": "competition_stage", "id": int(cfg["domain_id"])},
        "train_task_id": int(cfg["task_id"]),
        "competition_team_id": int(cfg["team_id"]),
        "experiment_id": int(cfg["exp_id"]),
        "start_time": {"timestamp": start.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "end_time": {"timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "queries": build_queries(cfg, groups),
    }
    resp = requests.post(f"{API_BASE}/{endpoint}", json=body,
                         headers=build_headers(token, endpoint), timeout=30)
    resp.raise_for_status()
    return resp.json()


def missing_config(cfg: dict) -> list:
    """返回缺失/为空的必需配置字段。"""
    return [f for f in REQUIRED_FIELDS if str(cfg.get(f, "")).strip() == ""]


def diagnose_status(cfg: dict) -> dict:
    """统一诊断 配置缺失 / token 过期 / 网络 / API 状态，返回结构化结果。

    返回 {status, need, message, ...}，status ∈ STATUS_INFO。
    Hermes 据此主动告知用户需要提供什么（URL 或 token）。
    """
    miss = missing_config(cfg)
    if miss:
        need = ["url"]
        if "token" in miss:
            need.append("token")
        return {"status": "missing_config", "need": need, "missing_fields": miss,
                "message": STATUS_INFO["missing_config"][2]}
    try:
        result = fetch_range(cfg, hours=0.1, groups=["quick_check"])
    except requests.RequestException as e:
        return {"status": "network_error", "need": [], "message": f"网络错误: {e}"}
    code = result.get("code", -1)
    if code == 0:
        return {"status": "ok", "need": [], "message": STATUS_INFO["ok"][2]}
    if code == 1401:
        return {"status": "token_expired", "need": ["token"],
                "message": STATUS_INFO["token_expired"][2]}
    return {"status": "api_error", "need": [], "code": code,
            "message": f"API 返回错误: code={code}, msg={result.get('msg', '')}"}


def print_status(status: dict, as_json: bool) -> None:
    """打印状态：as_json 时输出机器可解析 JSON，否则友好文本。"""
    if as_json:
        print(json.dumps(status, ensure_ascii=False))
        return
    icon = "✓" if status["status"] == "ok" else "✗"
    print(f"{icon} [{status['status']}] {status['message']}")
    if status.get("need"):
        print(f"  需要用户提供: {', '.join(status['need'])}")


def parse_url(url: str) -> dict:
    """从监控页面 URL 解析参数。兼容参数在 query(?...) 或 SPA fragment(#/...?...) 中。"""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse((url or "").strip())
    params = parse_qs(parsed.query)
    # SPA 监控页参数常挂在 # 片段，query 取不到时回退解析 fragment
    if parsed.fragment:
        frag = parsed.fragment.split("?", 1)[1] if "?" in parsed.fragment else parsed.fragment
        for k, v in parse_qs(frag).items():
            params.setdefault(k, v)
    keys = ["task_id", "task_uuid", "team_id", "domain_id", "exp_id"]
    return {k: params.get(k, [""])[0].strip() for k in keys}


def persist_data(data: dict, cfg: dict):
    """写 latest.json，并按 task_id 追加精简摘要到 history。"""
    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(common.LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    task_id = cfg.get("task_id", "unknown")
    metrics = common.summarize_metrics(data)
    train_step = metrics.get("train_step", {}).get("avg")
    record = {
        "ts": common.utcnow_iso(),
        "task_id": task_id,
        "train_step": train_step,
        "metrics": metrics,
    }
    hist_path = common.append_history(task_id, record)
    print(f"数据已保存: {common.LATEST_PATH}")
    print(f"长时段摘要已追加: {hist_path}")


def format_summary(data: dict, cfg: dict, hours: float) -> str:
    """人类可读摘要。"""
    lines = [
        f"=== 训练监控摘要 ({cfg.get('competition_stage', '未知')}, "
        f"task_id={cfg.get('task_id', '?')}, 最近{hours}h) ===",
        "",
    ]
    metrics = common.summarize_metrics(data)
    for name, s in metrics.items():
        lines.append(
            f"{name:28s} avg={s['avg']:>10.4f}  trend={s['trend']} {s['trend_pct']:>+6.1f}%  "
            f"cv={s['cv']:>5.2f}  min={s['min']:>9.4f}  max={s['max']:>9.4f}"
        )
    if len(lines) == 2:
        lines.append("(无数据)")
    return "\n".join(lines)


def format_structured(data: dict, cfg: dict, hours: float) -> str:
    """JSON 结构化摘要（便于解析）。"""
    summary = {
        "stage": cfg.get("competition_stage", "未知"),
        "task_id": cfg.get("task_id", "?"),
        "hours": hours,
        "metrics": common.summarize_metrics(data),
    }
    summary["metric_count"] = len(summary["metrics"])
    return json.dumps(summary, ensure_ascii=False, indent=2)


def handle_update_config(args, cfg) -> dict:
    """更新配置（token/url/task_id/stage），返回结构化结果供 Hermes 判断是否成功。"""
    changed = False
    applied = {}
    if args.token:
        cfg["token"] = args.token.strip()
        applied["token"] = "***"
        print("token 已更新")
        changed = True
    if args.url:
        parsed = parse_url(args.url)
        nonempty = {k: v for k, v in parsed.items() if v}
        if not nonempty:
            print("✗ URL 未解析出任何参数（参数可能在 # 片段中或格式不符），未更新 URL 相关字段")
        else:
            for k, v in nonempty.items():
                cfg[k] = v
                applied[k] = v
                print(f"{k} = {v}")
            changed = True
    if args.task_id:
        cfg["task_id"] = str(args.task_id).strip()
        applied["task_id"] = cfg["task_id"]
        print(f"task_id = {cfg['task_id']}")
        changed = True
    if args.stage:
        cfg["competition_stage"] = args.stage.strip()
        applied["competition_stage"] = cfg["competition_stage"]
        print(f"competition_stage = {cfg['competition_stage']}")
        changed = True
    if changed:
        common.save_local_config(cfg)
        print(f"配置已保存到 {common.LOCAL_CONFIG_PATH}")
    else:
        print("（无字段被更新）")

    miss = missing_config(cfg)
    if miss:
        print(f"⚠ 仍缺少必需字段: {', '.join(miss)}")
    return {"changed": changed, "applied": applied, "missing_fields": miss}


def main():
    parser = argparse.ArgumentParser(description="开悟平台训练监控数据抓取")
    parser.add_argument("--validate", action="store_true", help="验证 token 和连接")
    parser.add_argument("--hours", type=float, default=6, help="抓取最近 N 小时（默认 6）")
    parser.add_argument("--groups", nargs="*", help="指定指标组（默认全部）")
    parser.add_argument("--format", choices=["json", "summary", "structured"],
                        default="summary", help="输出格式")
    parser.add_argument("--no-persist", action="store_true", help="不持久化数据")
    parser.add_argument("--update-config", action="store_true", help="更新配置")
    parser.add_argument("--token", help="更新 token")
    parser.add_argument("--url", help="从监控页面 URL 解析参数")
    parser.add_argument("--task-id", help="更新 task_id")
    parser.add_argument("--stage", help="更新赛段")
    parser.add_argument("--json", action="store_true",
                        help="状态/错误以 JSON 输出（供 Hermes 解析分支）")
    args = parser.parse_args()

    cfg = common.load_config()

    # 更新配置：返回结构化结果，--json 时输出供 Hermes 判断是否还缺字段
    if args.update_config:
        result = handle_update_config(args, cfg)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if not result["missing_fields"] else STATUS_INFO["missing_config"][0])

    # 先做无网络的配置完整性检查，再决定是否探测/抓取
    miss = missing_config(cfg)
    if miss:
        need = ["url"] + (["token"] if "token" in miss else [])
        print_status({"status": "missing_config", "need": need, "missing_fields": miss,
                      "message": STATUS_INFO["missing_config"][2]}, args.json)
        sys.exit(STATUS_INFO["missing_config"][0])

    # --validate：轻量探针，输出状态并按状态退出码退出
    if args.validate:
        status = diagnose_status(cfg)
        print_status(status, args.json)
        sys.exit(STATUS_INFO.get(status["status"], (1,))[0])

    # 正式抓取（失败时同样给出可分支的状态）
    if not args.json:
        print(f"正在抓取最近 {args.hours} 小时的数据...")
    try:
        data = fetch_range(cfg, hours=args.hours, groups=args.groups)
    except requests.RequestException as e:
        print_status({"status": "network_error", "need": [], "message": f"网络错误: {e}"}, args.json)
        sys.exit(STATUS_INFO["network_error"][0])

    code = data.get("code", -1)
    if code != 0:
        st = "token_expired" if code == 1401 else "api_error"
        print_status({"status": st, "need": STATUS_INFO[st][1], "code": code,
                      "message": f"{STATUS_INFO[st][2]}（code={code}, msg={data.get('msg', '')}）"},
                     args.json)
        sys.exit(STATUS_INFO[st][0])

    if not args.no_persist:
        persist_data(data, cfg)

    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.format == "structured":
        print(format_structured(data, cfg, args.hours))
    else:
        print(format_summary(data, cfg, args.hours))


if __name__ == "__main__":
    main()
