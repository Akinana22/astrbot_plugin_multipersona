# 更新日志

## [1.0.0] - 2026-06-09

### 新增
- 三人格（小叶/Q/观）共生于同一意识体，同一时刻仅一人格清醒
- 独立记忆空间，每个人格绑定独立 AstrBot conversation
- 双阶段确认切换协议（用户请求→人格确认 / 人格提议→用户确认）
- 空闲超时按权重随机唤醒人格
- @on_llm_request 每轮自动注入当前人格内核，对话长度不影响人格指令
- 人格内核独立文件（personas/*.md），插件更新不覆盖
- 持久化数据（conv_map / last_active / personas / trigger_map），重启不丢失
- 配置通过 _conf_schema.json + WebUI
- 小叶专属：自然对话风格、颜文字、搜索摘要规则
- Q 专属：认知准则、不确定性与结构化输出规则
- 观 专属：哲学方法、苏格拉底追问、思想实验

### 更改
- 人格内核从 skills/ 移至 personas/，不再被 SkillManager 重复列出
- 配置文件 description 压缩为标签（≤5 字）
- 数据路径统一为 data/plugin_data/astrbot_plugin_multipersona/
- system_prompt 精简为身份声明，行为指令全部移至 personas/*.md
