# AI Multi-Persona Switch

[中文](README.md)

Three personas (Xiaoye / Q / Guan) coexisting in one consciousness, as an AstrBot plugin.
Independent memory spaces. Dual-phase consent switching. Weighted idle-time random awakening.
Persona kernels stored as AstrBot Skills, auto-injected per LLM request — never diluted.

---

## Features

- **Three Personas**: Xiaoye (life assistant), Q (tech expert), Guan (philosophy advisor) coexist in one consciousness. Only one is awake at a time.
- **Independent Memory**: Each persona has its own AstrBot conversation. They cannot see each other's chat history.
- **Dual-Phase Consent**: User requests require persona confirmation. Persona suggestions require user confirmation. No unilateral switching.
- **Weighted Idle Awakening**: After idle timeout, a persona is randomly selected based on configured weights.

---

## What is a Persona

**Persona** is AstrBot's native personality configuration system. Each persona is a database record
containing independent system_prompt, skills whitelist, tools whitelist, and begin_dialogs.

This plugin extends AstrBot Persona with:
- Multi-persona coexistence management
- Dual-phase consent switching protocol
- Independent memory (separate conversation per persona)
- Weighted random awakening on idle timeout
- Persona kernel auto-injection via SKILL.md (every LLM request)

---

## Configuration

After installation, configuration is stored at `data/config/astrbot_plugin_multipersona_config.json`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `personas_data_dir` | string | `""` | Persona data directory. Leave empty for auto `data/astrbot_plugin_multipersona/` |
| `idle_timeout_minutes` | int | `30` | Idle timeout in minutes. Set `0` to disable |
| `consent_timeout_rounds` | int | `3` | Max rounds waiting for consent before cancelling |
| `auto_create_personas` | bool | `true` | Auto-write personas to AstrBot DB on startup |
| `stop_event_after_switch` | bool | `true` | Stop the trigger message from forwarding to LLM after switch |

> **About `stop_event_after_switch`**: This refers to the **user message that triggered the switch**.
> Example: user says "let Q handle this" → trigger_map match → current persona consents → switch executed.
> With this on, Q won't receive the trigger message. Off = Q processes it again.

---

## Weights

Each persona's `weight` is stored in individual persistent files:

```
data/astrbot_plugin_multipersona/personas/<persona_id>.json
```

| Persona | persona_id | Default Weight | Awakening Probability |
|---------|-----------|----------------|----------------------|
| Xiaoye  | `xiaoye` | 50 | 50% |
| Q       | `q_tech` | 30 | 30% |
| Guan    | `guan_philosophy` | 20 | 20% |

Weights don't need to sum to 100. Probability = persona_weight ÷ sum_of_all_weights.

---

## Persona Kernels (SKILL.md)

Full persona kernels are stored as AstrBot Skills under the plugin's `skills/` directory:

```
skills/
  xiaoyecore/SKILL.md     — Xiaoye behavior (tone, style, boundaries, transition rituals)
  qcore/SKILL.md          — Q behavior (iron law, cognitive principles, output format)
  guancore/SKILL.md       — Guan behavior (philosophical method, questioning style, boundaries)
```

These files are auto-injected into the system_prompt **before every LLM request**.
Edit them directly to customize persona behavior. Plugin updates do not overwrite them.

---

## Switching Protocol

```
Scenario A: User requests switch
─────────────────────────────────
User: "let Q handle this"
  → Plugin matches trigger_map, target q_tech
  → Current persona receives the message, responds
  → Persona explicitly says "switching to Q" in response
  → Plugin detects consent → executes switch → shows transition text
  → Q takes over immediately

  If persona doesn't consent within 3 rounds → cancelled

Scenario B: Persona suggests switch
───────────────────────────────────
Persona: "...Q would handle this better."
  → Plugin detects suggest_phrases keywords
  → Enters AWAITING_USER_CONSENT state
  → User says "ok" / "switch" / "yes"
  → Plugin executes switch

  If user doesn't consent → suggestion cancelled
```

---

## Supported Platforms

| Platform | Adapter |
|----------|---------|
| QQ (OneBot) | aiocqhttp |
| QQ Official | qqofficial / qqofficial_webhook |
| Telegram | telegram |
| WeCom | wecom |
| Lark | lark |
| DingTalk | dingtalk |
| Discord | discord |
| Slack | slack |
| KOOK | kook |
| WebChat | webchat |

---

## Persistent Data

Runtime data is stored under the AstrBot data directory:

```
data/astrbot_plugin_multipersona/
├── personas/
│   ├── xiaoye.json              ← Xiaoye full definition
│   ├── q_tech.json              ← Q full definition
│   └── guan_philosophy.json     ← Guan full definition
└── trigger_map.json             ← Trigger mappings + user consent phrases
```

- **First run**: Plugin auto-creates above files with defaults.
- **Subsequent runs**: Reads existing files. Your edits won't be overwritten.
- Each persona's system_prompt, weight, transition text, and consent/suggest keywords are configurable here.

---

## Notes

- Switching relies on the LLM explicitly saying consent keywords in its response.
- Idle timeout is measured from the last user message.
- Persona kernel SKILL.md files live inside the plugin's `skills/` directory. Back up custom modifications before updating the plugin.
- `begin_dialogs` can be used to set each persona's "waking up" first message template.
