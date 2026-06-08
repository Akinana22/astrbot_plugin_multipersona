# 更新日志

## [1.0.0] - 2026-06-09

### 新增
- 三人格（小叶/Q/观）共生于同一意识体，插件管理切换
- 独立记忆空间：每个人格绑定独立 AstrBot conversation，互不可见
- 双阶段确认切换协议：用户请求需人格确认 / 人格提议需用户确认
- 空闲超时按权重随机唤醒：超时后按 weight 比例随机选择活跃人格
- `@on_llm_request` 每轮 LLM 请求前强制注入当前人格内核（`personas/<id>.md`），永不稀释
- 持久化数据：`conv_map.json`（会话映射）、`last_active.json`（活跃记录）、`personas/*.json`（人格定义）、`trigger_map.json`（触发词）
- `_conf_schema.json` 配置项通过 AstrBot WebUI 可调（空闲超时、确认超时、自动创建、阻止转发）
- 中英文 README + i18n（zh-CN / en-US）

### 人格内核
- 小叶：生活助理。自然语气、短句、颜文字、搜索结果精简总结。
- Q：技术专家。五步铁律、认知准则（不假设正确、反复推敲、主动索取信息）、结构化输出。
- 观：哲学顾问。概念解剖、逻辑重构、多传统对照、苏格拉底式追问。

### 技术细节
- 内核文件 `personas/<id>.md` 与 AstrBot Skill 系统解耦，不再被 SkillManager 重复列出
- 配置文件 `description` 字段压缩为简短标签，详细说明移至 `hint`
- 持久化路径固定为 `data/plugin_data/astrbot_plugin_multipersona/`
- `config` 参数改为可选，兼容 AstrBot 降级初始化路径
- `_config_path` 为 None 时自动兜底
- 插件重启后从持久化文件恢复会话映射和活跃状态
