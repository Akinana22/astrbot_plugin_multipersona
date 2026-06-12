# 更新日志

## [1.0.2] - 2026-06-11

### 修复
- session 切换以插件持久化文件为准，不再依赖 AstrBot 数据库验证
- 单段回复（无句号）情绪标签无法转换的问题
- 新增切换全链路日志（handle_message / on_response / _execute_switch）

## [1.0.1] - 2026-06-11

### 新增
- 文件系统会话存储（sessions/<platform>/<user>/<pid>.json），按平台和用户隔离
- Cron 情绪标签转换（@on_using_llm_tool），定时任务消息中的 [happy:1] 等标签自动转为颜文字
- 切换后 LLM 主动打招呼（注入唤醒指令）

### 更改
- 移除 _conv_map 内存字典，会话改用文件系统管理
- _execute_switch 重写：存在旧 session 则 switch_conversation 恢复，不存在则新建
