# Gateway Bridge Code Config Pitfall

**Date discovered:** 2026-05-24
**Hermes version:** v0.14.0
**Severity:** High — silently ignores all `platforms.*` config

## Root Cause

`gateway/config.py` has two config loading paths:

1. **Section merge** (L768-788): Reads `platforms.*` and merges into `gw_data["platforms"]`. This works correctly.
2. **Bridge loop** (L809-881): Uses `yaml_cfg.get(plat.value)` to read **top-level** YAML keys. This is the broken path.

The bridge loop is responsible for writing platform settings into the `extra` dict and environment variables. Since it reads top-level keys (which are usually `None`), all `platforms.*` settings are silently skipped.

## Code Path

```python
# config.py L824 (bridge loop)
for plat in Platform:
    platform_cfg = yaml_cfg.get(plat.value)  # reads top-level key, NOT platforms.*
    if not platform_cfg:
        continue  # ← ALL platforms.* settings skipped here
    # ... bridge settings into extra dict
```

## What Works vs What Doesn't

| Config location | Bridge reads? | Env var fallback? | Reliable? |
|----------------|---------------|-------------------|-----------|
| `platforms.feishu.require_mention` | ❌ No | Yes (`FEISHU_REQUIRE_MENTION`) | ✅ Via env var |
| `platforms.feishu.allow_bots` | ❌ No | Yes (`FEISHU_ALLOW_BOTS`) | ✅ Via env var |
| `platforms.feishu.reply_to_mode` | ❌ No | ❌ No env var | ❌ Dead config |
| `platforms.feishu.guest_mode` | ❌ No | ❌ No env var | ❌ Dead config (also Telegram-only) |
| Top-level `feishu.require_mention` | ✅ Yes | N/A | ✅ Works |
| Env var `FEISHU_REQUIRE_MENTION=true` | N/A | N/A | ✅ Always works |

## Affected Platforms

ALL platforms are affected — the bridge code pattern is shared:

- Feishu: `yaml_cfg.get("feishu")`
- Telegram: `yaml_cfg.get("telegram")`
- Slack: `yaml_cfg.get("slack")`
- Discord: `yaml_cfg.get("discord")`
- WhatsApp: `yaml_cfg.get("whatsapp")`
- Signal: `yaml_cfg.get("signal")`
- DingTalk: `yaml_cfg.get("dingtalk")`
- Mattermost: `yaml_cfg.get("mattermost")`
- Matrix: `yaml_cfg.get("matrix")`

## Recommendation

1. **Always use environment variables** for platform config in `~/.hermes/.env`
2. If using config.yaml, write under the **top-level** key (e.g., `feishu:` not `platforms.feishu:`)
3. `reply_to_mode` and `guest_mode` are **Telegram-only** — they have no implementation in Feishu adapter

## Verification

```bash
# Check if env var is set
env | grep FEISHU_REQUIRE_MENTION

# Check config.yaml for problematic platforms.* entries
grep -A 10 "^platforms:" ~/.hermes/config.yaml

# Restart gateway after changes
hermes gateway restart
```
