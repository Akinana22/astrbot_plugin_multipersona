import re

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter, MessageEventResult


def _norm_tools(val):
    """None → None (所有工具), [] → [] (禁用), [list] → [list] (过滤)"""
    if val is None or (isinstance(val, list) and len(val) == 0):
        return None if isinstance(val, list) and len(val) == 0 else val
    if isinstance(val, list):
        return val
    return None


class Main(star.Star):
    """
    多重人格切换插件。
    用户可通过"让Q来""让观来""小叶回来"等关键词切换 AstrBot 当前会话的 Persona。
    人格定义和触发词均可通过 _conf_schema.json → data/config 配置文件覆盖。
    """

    def __init__(self, context: star.Context, config: star.StarConfig) -> None:
        super().__init__(context)
        self.config = config
        self._init_done = False

    async def initialize(self) -> None:
        if self._init_done:
            return
        if self.config.get("auto_create_personas", True):
            await self._ensure_personas_in_db()
        self._init_done = True

    # ── Persona 数据库同步 ──────────────────────────────

    async def _ensure_personas_in_db(self):
        pm = self.context.persona_manager
        db = self.context.get_db()
        for pdef in self.config.get("personas", []):
            pid = pdef["persona_id"]
            existing = await db.get_persona_by_id(pid)
            if existing:
                continue
            await pm.create_persona(
                persona_id=pid,
                system_prompt=pdef.get("system_prompt", ""),
                begin_dialogs=pdef.get("begin_dialogs") or [],
                tools=_norm_tools(pdef.get("tools")),
                skills=_norm_tools(pdef.get("skills")),
                custom_error_message=pdef.get("custom_error_message"),
            )

    # ── 人格切换指令 ────────────────────────────────────

    @filter.regex(r"(?i)(让.*[Qq观].*来|叫.*[Qq观]|切.*[Qq观]|"
                  r"小叶.*回来|小叶.*接手|换个.*人格|切换.*人格|"
                  r"技术.*人格|哲学.*人格)")
    async def switch_persona(self, event: AstrMessageEvent) -> None:
        msg = event.get_message_str().strip()
        umo = event.unified_msg_origin

        target_pid = self._match_trigger(msg)
        if target_pid is None:
            p = self._find_persona("xiaoye")
            nm = (p or {}).get("display_name", "xiaoye")
            event.set_result(MessageEventResult().message(
                f"未识别目标人格。试试：让Q来 / 让观来 / 小叶回来\n当前可用人格：{self._list_persona_hints()}"
            ))
            event.stop_event()
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            plat_id = event.get_platform_name() or event.get_platform_id()
            await self.context.conversation_manager.new_conversation(
                umo, plat_id or "", persona_id=target_pid,
            )
        else:
            await self.context.conversation_manager.update_conversation_persona_id(
                umo, target_pid, cid,
            )

        pdef = self._find_persona(target_pid) or {}
        display = pdef.get("display_name", target_pid)
        event.set_result(MessageEventResult().message(f"已切换到 {display}"))

        if self.config.get("stop_event_after_switch", True):
            event.stop_event()

    # ── 查询当前人格 ─────────────────────────────────────

    @filter.regex(r"(当前.*(人格|身份|角色)|(谁在|谁在.|现在是谁))")
    async def show_persona(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            event.set_result(MessageEventResult().message("当前没有活跃对话。"))
            event.stop_event()
            return
        conv = await self.context.conversation_manager.get_conversation(umo, cid)
        pid = (conv and conv.persona_id) or ""
        if not pid:
            event.set_result(MessageEventResult().message("当前使用默认人格。"))
        else:
            pdef = self._find_persona(pid) or {}
            nm = pdef.get("display_name", pid)
            event.set_result(MessageEventResult().message(f"当前人格：{nm}"))
        event.stop_event()

    # ── 列出可用人格 ─────────────────────────────────────

    @filter.command("personas")
    async def list_personas(self, event: AstrMessageEvent) -> None:
        pids = [p["persona_id"] for p in self.config.get("personas", [])]
        await self.context.send_message(
            event.unified_msg_origin,
            f"可用人格：{', '.join(pids)}"
        )

    # ── helpers ──────────────────────────────────────────

    def _match_trigger(self, msg: str) -> str | None:
        for rule in self.config.get("trigger_map", []):
            pattern = rule.get("regex", "")
            if pattern and re.search(pattern, msg):
                return rule.get("persona_id")
        return None

    def _find_persona(self, persona_id: str) -> dict | None:
        for p in self.config.get("personas", []):
            if p.get("persona_id") == persona_id:
                return p
        return None

    def _list_persona_hints(self) -> str:
        parts = []
        for p in self.config.get("personas", []):
            parts.append(p.get("display_name", p["persona_id"]))
        return "、".join(parts)
