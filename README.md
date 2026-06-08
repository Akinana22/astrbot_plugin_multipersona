# AI 多重人格切换

[English](README.en.md)

三人格（小叶 / Q / 观）共生于同一意识体的 AstrBot 插件。
独立记忆空间，双阶段确认切换协议，空闲超时按权重随机唤醒。
人格内核以 AstrBot Skill 形式存放，插件在每轮 LLM 请求中自动注入，永不稀释。

---

## 功能

- **三人格共生**：小叶（生活助理）、Q（技术专家）、观（哲学顾问）共存于同一意识体。同一时刻仅一人格清醒。
- **独立记忆空间**：每个人格拥有独立的 AstrBot conversation。切换后看不到其他人格的对话历史。
- **双阶段确认切换**：用户请求时需人格确认同意；人格提议时需用户确认同意。不会擅自切换。
- **空闲超时随机唤醒**：超过设定时间无消息后，按权重随机选择活跃人格。

---

## 什么是 Persona

**Persona** 是 AstrBot 框架的原生人格设定模块。每个人格是 AstrBot 数据库中的一条记录，
包含独立的 system_prompt、skills 白名单、tools 白名单、begin_dialogs 等配置。

本插件在 AstrBot Persona 基础上增加了：
- 三人格共存管理
- 双阶段确认切换协议
- 独立记忆空间（每个人格绑定独立 conversation）
- 空闲超时权重随机唤醒
- 人格内核 via SKILL.md 自动注入（每轮 LLM 请求）

---

## 配置

插件安装后，配置位于 `data/config/astrbot_plugin_multipersona_config.json`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `personas_data_dir` | string | `""` | 人格持久化数据目录。留空则自动使用 `data/astrbot_plugin_multipersona/` |
| `idle_timeout_minutes` | int | `30` | 空闲超时（分钟）。设为 `0` 禁用 |
| `consent_timeout_rounds` | int | `3` | 等待人格/用户确认的最大对话轮数 |
| `auto_create_personas` | bool | `true` | 启动时自动写入 AstrBot Persona 数据库 |
| `stop_event_after_switch` | bool | `true` | 切换后是否阻止触发消息继续传给 LLM |

> **关于 `stop_event_after_switch`**：指**触发切换的那条用户消息**。
> 例如：用户说"让Q来"，匹配 trigger_map → 小叶回应后同意切换 → 插件执行切换。
> 开关起时，该条"让Q来"不再传给 Q；关时，Q 会再收到这条消息并处理一遍。

---

## 权重

每个人格的 `weight` 存储在独立的持久化文件中：

```
data/astrbot_plugin_multipersona/personas/<persona_id>.json
```

| 人格 | persona_id | 默认权重 | 空闲唤醒概率 |
|------|-----------|---------|-------------|
| 小叶 | `xiaoye` | 50 | 50% |
| Q    | `q_tech` | 30 | 30% |
| 观   | `guan_philosophy` | 20 | 20% |

权重总和不必为 100。概率 = 该人格权重 ÷ 所有人格权重之和。

---

## 人格内核（SKILL.md）

每个人格的完整内核以 AstrBot Skill 格式存放在插件目录的 `skills/` 下：

```
skills/
  xiaoyecore/SKILL.md     — 小叶完整行为指令（语气、风格、边界、切换仪式）
  qcore/SKILL.md          — Q 完整行为指令（铁律、认知准则、输出格式）
  guancore/SKILL.md       — 观 完整行为指令（思辨方法、追问风格、边界）
```

这些文件由插件在**每轮 LLM 请求前**自动注入到 system_prompt，不受对话长度影响。

你可以直接编辑这些 SKILL.md 来定制人格行为。插件不会覆盖它们。

---

## 切换协议

```
场景 A：用户主动请求
─────────────────────────
用户: "让Q来"
  → 插件匹配 trigger_map，目标 q_tech
  → 当前人格（如小叶）收到该消息，回应
  → 小叶在回复中明确说 "切换为Q"
  → 插件检测到 → 执行切换 → 显示过渡文字
  → Q 接管，下一条消息由 Q 回应

  如果小叶未在三轮内明确同意 → 取消切换

场景 B：人格主动提议
─────────────────────────
人格（如小叶）: "...这个问题 Q 来处理更合适。"
  → 插件检测到 suggest_phrases 中的关键词
  → 进入等待用户确认状态
  → 用户说 "好" / "切到Q" / "同意"
  → 插件执行切换

  如果用户说的不是同意 → 取消提议
```

---

## 平台支持

| 平台 | 适配器 |
|------|--------|
| QQ (OneBot) | aiocqhttp |
| QQ 官方 | qqofficial / qqofficial_webhook |
| Telegram | telegram |
| 企业微信 | wecom |
| 飞书 | lark |
| 钉钉 | dingtalk |
| Discord | discord |
| Slack | slack |
| KOOK | kook |
| WebChat | webchat |

---

## 持久化数据

插件运行时数据存放在 AstrBot 数据目录下：

```
data/astrbot_plugin_multipersona/
├── personas/
│   ├── xiaoye.json              ← 小叶完整定义
│   ├── q_tech.json              ← Q 完整定义
│   └── guan_philosophy.json     ← 观 完整定义
└── trigger_map.json             ← 触发词映射 + 用户同意关键词
```

- **首次启动**：插件自动创建上述文件，写入默认值。
- **后续启动**：直接读取。你编辑的文件不会被插件更新覆盖。
- 每个人格的 system_prompt、weight、transition 文字、consent/suggest 关键词均在此配置。

---

## 注意事项

- 切换协议依赖 LLM 在回复中明确说出 `切换为X` 等关键词。若人格未在 `consent_phrases` 内表述，切换不会触发。
- 空闲超时计时从最后一条用户消息开始算。
- 人格内核 SKILL.md 位于插件目录内的 `skills/`，更新插件时请注意备份自定义修改。
- `begin_dialogs` 可用于设置每个人格"醒来"时的第一句话模板。
