# 更新日志

## [1.0.0] - 2026-06-09

### 新增
- 三人格（小叶/Q/观）共生于同一意识体，同一时刻仅一人格清醒
- 独立记忆空间，每个人格绑定独立 AstrBot conversation
- 双阶段确认切换协议（用户请求→人格确认 / 人格提议→用户确认）
- 空闲超时按权重随机唤醒人格
- @on_llm_request 每轮自动注入当前人格内核，永不稀释
- 人格内核独立文件（personas/*.md），插件更新不覆盖
- 持久化会话数据（conv_map / last_active），重启不丢失
- 持久化配置数据（personas/*.json / trigger_map.json），用户修改不随插件更新覆盖
- 配置通过 _conf_schema.json + WebUI 管理
- 小叶专属：自然对话风格、颜文字、搜索摘要规则
- Q 专属：认知准则、不确定性与结构化输出规则
- 观 专属：哲学思辨方法、心理学视角（CBT/依恋/防御机制/存在主义心理）、临床安全边界
- 中英文 README + i18n 国际化

### 更改
- 人格内核从 skills/ 移至 personas/，不再被 AstrBot SkillManager 重复列出
- 配置文件 description 压缩为标签（≤5 字）
- 持久化数据路径统一为 data/plugin_data/astrbot_plugin_multipersona/
- system_prompt 精简为身份声明，行为指令全部移至 personas/*.md
- 移除 docs/ 历史设计稿目录
