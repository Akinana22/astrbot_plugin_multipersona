# 更新日志

## [1.0.1] - 2026-06-11

### 新增
- 文件系统会话存储（sessions/<platform>/<user>/<pid>.json），按平台和用户隔离
- Cron 情绪标签转换（@on_using_llm_tool），定时任务消息中的 [happy:1] 等标签自动转为颜文字
- 切换后 LLM 主动打招呼（注入唤醒指令）

### 更改
- 移除 _conv_map 内存字典，会话改用文件系统管理
- _execute_switch 重写：存在旧 session 则 switch_conversation 恢复，不存在则新建
