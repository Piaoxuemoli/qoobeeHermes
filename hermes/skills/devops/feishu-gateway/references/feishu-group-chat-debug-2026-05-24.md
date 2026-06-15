# Feishu Group Chat Debugging Session — 2026-05-24

## Problem
Bot added to group chat `oc_8ce246fa37c8b15f1045f42e8e6a15fe` but @mentioning it produced no response.

## Diagnosis Steps

### Phase 1: Initial Diagnosis
1. **Checked gateway status** — service running, Feishu WebSocket connected
2. **Checked gateway logs** — found `Bot added to chat: oc_8ce246fa37c8b15f1045f42e8e6a15fe` at 21:28:13
3. **Scanned all logs** — NO `Inbound group message received` entries for that chat_id
4. **All inbound messages** were `Inbound dm message` from the DM chat `oc_643a98910cab28158ee3c04fe5ef5d03`
5. **Checked env vars** — `FEISHU_GROUP_POLICY=allowall`, `FEISHU_REQUIRE_MENTION` not set (defaults to `true`)

### Phase 2: Differential Diagnosis (Key Insight)
Checked which events ARE being received from the group chat:

| Time | Event Type | Status |
|------|-----------|--------|
| 21:28:13 | `Bot added to chat` | ✅ |
| 21:54:22 | `reaction:added:Get` | ✅ |
| 22:41:16 | `reaction:added:THUMBSUP` | ✅ |
| - | Text messages | ❌ Never received |

**This differential diagnosis is critical:** Reactions (`im.message.reaction.created_v1`) work but text messages (`im.message.receive_v1`) don't. These are separate event subscriptions — the presence of one does not guarantee the other.

### Phase 3: Deep Code Analysis
Key code locations in `gateway/platforms/feishu.py`:

- `_admit()` method (line 4002): Admission control for all inbound messages
  - Line 4034: `if require_mention and not self._mentions_self(message): return "group_policy_rejected"`
  - **IMPORTANT:** Rejection is logged at DEBUG level (line 2415): `logger.debug("[Feishu] dropping inbound event: %s", reason)`
  - gateway.log only shows INFO+, so silently dropped messages leave NO trace
- `_require_mention_for()` (line 4038): Per-chat mention requirement check
- `_mentions_self()` (line 4091): @mention detection (checks `@_all`, mentions list, normalized text)
- `_allow_group_message()` (line 4046): Group policy check
- `require_mention` defaults to `true` (line 1569-1570): `extra.get("require_mention", os.getenv("FEISHU_REQUIRE_MENTION", "true"))`

### Phase 4: App ID Verification
User's key insight: "是不是应用没有使用正确的token导致的" (Is the app not using the correct token?)

Current config:
```
FEISHU_APP_ID=cli_aa9846a4e678dbc1
```

**If event subscription is on a different Feishu app than the one Hermes connects to, events won't be received.** This is a common misconfiguration when users have multiple Feishu apps.

## Resolution Status (as of session end)
- Set `FEISHU_REQUIRE_MENTION=false` in `.env` — eliminates @mention requirement
- Gateway restarted multiple times
- **Text messages still not received** — root cause is `im.message.receive_v1` event subscription issue on the Feishu platform side
- Pending: User to verify App ID match and event subscription status in Feishu developer console

## Key Takeaways

1. **Differential diagnosis is essential** — Check which event types work (reactions, bot-added) vs. which don't (text messages). This immediately narrows the problem to specific event subscriptions.

2. **DEBUG-level silent drops** — The `_admit()` method logs rejections at DEBUG level. Don't assume messages aren't arriving; they may be arriving and being silently dropped. Enable DEBUG logging or check the differential.

3. **App ID mismatch** — Always verify `FEISHU_APP_ID` in `.env` matches the App ID shown in the Feishu developer console. Users with multiple apps commonly subscribe events to the wrong one.

4. **Event subscriptions require app publishing** — Adding an event subscription in draft mode doesn't activate it. A new version must be published.

5. **Separate event subscriptions** — `im.message.reaction.created_v1` and `im.message.receive_v1` are independent. One working does not guarantee the other.
