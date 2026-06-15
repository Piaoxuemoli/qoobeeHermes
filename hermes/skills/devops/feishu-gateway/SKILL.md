---
name: feishu-gateway
description: "Configure, troubleshoot, and operate the Feishu (Lark) gateway integration — group chats, @mention gating, permissions, message routing, and diagnostics."
version: 1.0.0
author: Hermes
metadata:
  hermes:
    tags: [feishu, lark, gateway, group-chat, messaging, configuration]
    related_skills: [hermes-agent]
---

# Feishu Gateway

Configure and troubleshoot the Feishu/Lark messaging platform integration in Hermes Agent.

## When to Load

- User asks about Feishu bot not responding in group chats
- User wants to configure group chat behavior (@mention requirements)
- Debugging Feishu message routing issues
- Setting up Feishu bot for the first time

## Quick Reference

### Key Environment Variables (`~/.hermes/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `FEISHU_APP_ID` | required | Feishu app ID (from developer console) |
| `FEISHU_APP_SECRET` | required | Feishu app secret |
| `FEISHU_CONNECTION_MODE` | `websocket` | `websocket` or `webhook` |
| `FEISHU_REQUIRE_MENTION` | `true` | Whether bot requires @mention in group chats |
| `FEISHU_GROUP_POLICY` | `allowlist` | Group message policy: `open`, `allowlist`, `blacklist`, `admin_only`, `disabled` |
| `FEISHU_ALLOWED_USERS` | empty | Comma-separated user IDs for allowlist policy |

### Group Chat @Mention Behavior

**Default:** Bot only responds in group chats when explicitly @mentioned. This is controlled by `FEISHU_REQUIRE_MENTION` (defaults to `true`).

To make bot respond to ALL messages in group chats (no @mention required):
```bash
# In ~/.hermes/.env
FEISHU_REQUIRE_MENTION=false
# Then restart:
hermes gateway restart
```

### Config in `config.yaml`

**⚠️ WARNING: Do NOT put Feishu platform settings under `platforms.feishu`!**

The gateway bridge code (`config.py` L824) reads from the **top-level** YAML key (`yaml_cfg.get("feishu")`), NOT from `platforms.feishu`. Settings written under `platforms.feishu` are silently ignored by the bridge. This is a known Hermes v0.14.0 design issue.

**Correct approach:** Use environment variables in `~/.hermes/.env` for ALL Feishu platform settings. See the env var table above.

**If you must use config.yaml** (not recommended), write under the top-level `feishu:` key:
```yaml
feishu:
  require_mention: true
```

**Do NOT write:**
```yaml
# ❌ THIS DOES NOT WORK — bridge code never reads this
platforms:
  feishu:
    require_mention: true
```

Note: `reply_to_mode` and `guest_mode` are **Telegram-only** features and have no effect on Feishu.

## Diagnostics

### Check Gateway Status
```bash
hermes gateway status
```

### View Feishu Logs
```bash
grep -i feishu ~/.hermes/logs/gateway.log | tail -30
```

### Key Log Patterns

| Log Entry | Meaning |
|-----------|---------|
| `Bot added to chat: <chat_id>` | Bot successfully joined a group |
| `Bot removed from chat: <chat_id>` | Bot was removed from a group |
| `Inbound dm message received` | Message from a 1-on-1 chat |
| `Inbound group message received` | Message from a group chat |
| `dropping inbound event: group_policy_rejected` | Message blocked by group policy or @mention requirement |
| `dropping inbound event: bots_disabled` | Bot messages are not allowed |

**⚠️ Pitfall:** The `_admit()` method logs rejections at **DEBUG level**, not INFO. gateway.log only shows INFO+, so silently dropped messages leave **no trace**. If you suspect messages are being rejected, use differential diagnosis (check if reactions work but text messages don't) rather than looking for rejection log entries.

### Sending Messages to a Chat

```python
# Via send_message tool
send_message(action="send", target="feishu:<chat_id>", message="Hello!")
```

## Common Issues

### 1. Bot Not Responding in Group Chat

**Symptoms:** Bot is added to group but @mentioning it produces no response.

**Diagnosis:**
1. Check gateway logs for `Inbound group message received` — if absent, bot isn't receiving events
2. If present but `group_policy_rejected`, check @mention and policy settings

**Causes:**
- `FEISHU_REQUIRE_MENTION=true` (default) — user must @mention the bot
- `FEISHU_GROUP_POLICY=allowlist` (default) — sender must be in `FEISHU_ALLOWED_USERS`
- Feishu developer console missing `im.message.receive_v1` event subscription

**Fix:** See [Pitfall #1](#pitfalls) — use environment variables only.
```bash
# Option A: Allow all users, no @mention required
echo 'FEISHU_GROUP_POLICY=open' >> ~/.hermes/.env
echo 'FEISHU_REQUIRE_MENTION=false' >> ~/.hermes/.env
hermes gateway restart

# Option B: Keep allowlist but add specific users
echo 'FEISHU_ALLOWED_USERS=ou_xxx,ou_yyy' >> ~/.hermes/.env
hermes gateway restart
```

### 2. Bot Receives DMs but Not Group Messages

**Symptoms:** Bot responds in DM but group messages are silent.

**Diagnosis — 3-step differential:**

1. Check if **reaction events** work in the group chat (e.g., add a 👍 to a bot message)
   - ✅ Reactions work → `im.message.reaction.created_v1` subscription is fine
   - ❌ Reactions don't work → broader event delivery issue
2. Check if **bot added/removed** events logged (`Bot added to chat: <id>`)
   - ✅ Logged → `im.chat.member.bot.added_v1` subscription is fine
3. If reactions work but text messages don't → **`im.message.receive_v1` subscription issue**

**Why reactions work but text messages don't:** These are separate event subscriptions in Feishu. The bot can receive `im.message.reaction.created_v1` without `im.message.receive_v1` being enabled.

**Critical debugging note:** The `_admit()` method (line ~4002) rejects messages at **DEBUG level** (`logger.debug("[Feishu] dropping inbound event: %s", reason)`). Since gateway.log only shows INFO+, silently rejected messages leave **no trace** in logs. Don't assume messages aren't arriving — they may be arriving and being dropped.

**Causes (in order of likelihood):**
1. `im.message.receive_v1` event not subscribed in Feishu developer console
2. Event subscribed to a **different Feishu app** than the one Hermes is configured with (check `FEISHU_APP_ID` matches the app in developer console)
3. App version not published after adding event subscription (draft changes don't take effect)
4. Missing permission scopes: `im:message.group_at_msg`, `im:message.group_at_msg:readonly`

**Fix:** In [Feishu Open Platform](https://open.feishu.cn/):
1. Go to your app → **Event & Callback** → ensure `im.message.receive_v1` is subscribed
2. **Verify App ID matches** — check `App ID` in developer console matches `FEISHU_APP_ID` in `~/.hermes/.env`
3. Ensure bot has `im:message` or `im:message.receive_v1` permission scope
4. **Publish a new version** if you just added the event subscription
5. Restart gateway: `hermes gateway restart`

### 3. Messages Received but Not Routed to Group Chat

**Symptoms:** Logs show messages received as `Inbound dm message` even in group context.

**Cause:** Feishu WebSocket may deliver group messages with `chat_type=p2p` if the bot was recently added.

**Fix:** Restart gateway after adding bot to a new group:
```bash
hermes gateway restart
```

## Pitfalls

### 1. `platforms.feishu` config is SILENTLY IGNORED

**Root cause:** `config.py` L824 uses `yaml_cfg.get(plat.value)` which reads YAML top-level keys (e.g., `feishu:` at root), NOT `platforms.feishu`. The `hermes config set` command writes to `platforms.*`, which the bridge never reads.

**Impact:** `require_mention`, `allow_bots`, and ALL other platform settings written under `platforms.feishu` are dead config.

**Fix:** Use environment variables (`FEISHU_REQUIRE_MENTION`, `FEISHU_ALLOW_BOTS`, etc.) in `~/.hermes/.env`. These are read by `config.py` L1063-1134 env-var mapping as the final fallback.

**Affected platforms:** This issue applies to ALL platforms (Telegram, Slack, Discord, etc.), not just Feishu. The bridge code pattern `yaml_cfg.get(plat.value)` is shared across all platforms (L809-881).

**Detailed analysis:** See `references/bridge-code-config-pitfall.md`

### 2. `_admit()` rejection logging at DEBUG level

The `_admit()` method logs rejections at **DEBUG level**, not INFO. gateway.log only shows INFO+, so silently dropped messages leave **no trace**. Use differential diagnosis (check if reactions work but text messages don't) rather than looking for rejection log entries.

## Reference Files

- `references/feishu-group-chat-debug-2026-05-24.md` — Real debugging session: bot added to group but not responding

## Architecture Notes

- Feishu adapter: `gateway/platforms/feishu.py` (~5100 lines)
- Message admission logic: `_admit()` method (line ~4002)
- @mention detection: `_mentions_self()` method (line ~4091)
- Group policy check: `_allow_group_message()` method (line ~4046)
- Events registered: `im.message.receive_v1`, `im.message.reaction.created_v1`, `im.chat.member.bot.added_v1`, etc.
- Bot identity: Uses `open_id` (app-scoped) for mention matching
