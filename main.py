import asyncio
import os
import random
import re
import time

from astrbot.api import AstrBotConfig, star
from astrbot.api.event import AstrMessageEvent, filter, MessageEventResult

# ── 状态机常量 ─────────────────────────────────────────
IDLE = 0
AWAITING_PERSONA_CONSENT = 1
AWAITING_USER_CONSENT = 2


def _norm_list(val):
    """None → None, [] → [], [list] → [list]"""
    if val is None:
        return None
    if isinstance(val, list):
        return val
    return None


def _strip_frontmatter(text: str) -> str:
    """剥掉 SKILL.md 的 YAML frontmatter，返回正文内容。"""
    if not text.startswith("---"):
        return text
    idx = text.find("---", 3)
    if idx == -1:
        return text
    return text[idx + 3:].strip()


def _extract_response_text(response) -> str:
    """从 OnLLMResponseEvent 的 response 中提取纯文本。"""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if hasattr(response, "completion_text"):
        return getattr(response, "completion_text") or ""
    if hasattr(response, "get"):
        return response.get("completion_text") or ""
    return str(response)


class Main(star.Star):
    """
    多人格切换插件（astrbot_plugin_multipersona）。

    核心设计：
    - 每个 Persona 的极简 system_prompt 只在 AstrBot 数据库中
    - 完整人格内核放在 skills/<core_skill_name>/SKILL.md
    - @on_llm_request 每轮注入当前人格的 SKILL.md，永不稀释
    - 独立记忆空间：每个人格独立 conversation
    - 双阶段确认切换协议
    - 空闲超时按权重随机唤醒
    """

    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self._init_done = False

        # umo → {persona_id: cid}
        self._conv_map: dict[str, dict[str, str]] = {}

        # umo → (persona_id, timestamp)
        self._last_active: dict[str, tuple[str, float]] = {}

        # umo → {state, target_pid, trigger_pid, rounds, timestamp}
        self._switch_state: dict[str, dict] = {}

        # 内核缓存: core_skill_name → content
        self._kernel_cache: dict[str, str] = {}

    # ── 生命周期 ────────────────────────────────────────

    async def initialize(self) -> None:
        if self._init_done:
            return
        if self.config.get("auto_create_personas", True):
            await self._ensure_personas_in_db()
        self._preload_kernels()
        self._init_done = True

    async def terminate(self) -> None:
        self._conv_map.clear()
        self._last_active.clear()
        self._switch_state.clear()
        self._kernel_cache.clear()

    # ── Persona 数据库初始化 ─────────────────────────────

    async def _ensure_personas_in_db(self):
        pm = self.context.persona_manager
        db = self.context.get_db()
        for pdef in self.config.get("personas", []):
            pid = pdef.get("persona_id")
            if not pid:
                continue
            existing = await db.get_persona_by_id(pid)
            if existing:
                continue
            await pm.create_persona(
                persona_id=pid,
                system_prompt=pdef.get("system_prompt", ""),
                begin_dialogs=pdef.get("begin_dialogs") or [],
                tools=_norm_list(pdef.get("tools")),
                skills=_norm_list(pdef.get("skills")),
                custom_error_message=pdef.get("custom_error_message"),
            )

    # ── 内核预加载 ──────────────────────────────────────

    def _preload_kernels(self):
        skills_dir = os.path.join(os.path.dirname(__file__), "skills")
        for pdef in self.config.get("personas", []):
            core = pdef.get("core_skill_name")
            if not core:
                continue
            skill_md = os.path.join(skills_dir, core, "SKILL.md")
            if os.path.isfile(skill_md):
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        self._kernel_cache[core] = _strip_frontmatter(f.read())
                except Exception:
                    pass

    def _load_kernel(self, persona_id: str) -> str:
        pdef = self._find_persona(persona_id)
        if not pdef:
            return ""
        core = pdef.get("core_skill_name", "")
        return self._kernel_cache.get(core, "")

    # ── 人格内核注入 ────────────────────────────────────

    @filter.on_llm_request()
    async def inject_persona_kernel(self, event, req):
        pid = await self._resolve_current_persona_id(event)
        kernel = self._load_kernel(pid)
        if kernel:
            req.system_prompt = kernel + "\n\n" + req.system_prompt

    # ── 消息拦截：切换请求 / 用户确认 / 空闲检测 ─────────

    @filter.regex(
        r"(?i)(让.*[Qq观].*来|叫.*[Qq观]|切.*[Qq观]|"
        r"小叶.*回来|小叶.*接手|换个.*人格|切换.*人格|"
        r"换.*[Qq观]|叫.*出来|[Qq观].*上|交给.*[Qq观]|"
        r"同意|可以|好的|行|切换|切到|切.*换)"
    )
    async def handle_message(self, event: AstrMessageEvent) -> None:
        msg = event.get_message_str().strip()
        umo = event.unified_msg_origin

        # 1. 空闲超时 → 随机唤醒
        await self._check_idle_timeout(umo, event)

        # 2. AWAITING_USER_CONSENT → 检查用户同意
        st = self._switch_state.get(umo)
        if st and st["state"] == AWAITING_USER_CONSENT:
            elapsed = time.time() - st.get("timestamp", 0)
            timeout_secs = self.config.get("consent_timeout_rounds", 3) * 60
            if elapsed > timeout_secs:
                self._switch_state.pop(umo, None)
            elif self._is_user_consent(msg):
                await self._execute_switch(
                    umo, st["target_pid"], event,
                    trigger_msg=msg,
                )
                self._switch_state.pop(umo, None)
                if self.config.get("stop_event_after_switch", True):
                    event.stop_event()
                return
            else:
                self._switch_state.pop(umo, None)
                return

        # 3. AWAITING_PERSONA_CONSENT → 新的请求重置计时
        if st and st["state"] == AWAITING_PERSONA_CONSENT:
            st["timestamp"] = time.time()
            return

        # 4. IDLE → 匹配触发词
        target_pid = self._match_trigger(msg)
        if not target_pid:
            return

        current_pid = await self._resolve_current_persona_id(event)
        if current_pid == target_pid:
            pdef = self._find_persona(target_pid) or {}
            nm = pdef.get("display_name", target_pid)
            event.set_result(MessageEventResult().message(f"已经是 {nm} 了。"))
            event.stop_event()
            return

        # 进入 AWAITING_PERSONA_CONSENT 状态
        self._switch_state[umo] = {
            "state": AWAITING_PERSONA_CONSENT,
            "target_pid": target_pid,
            "trigger_pid": current_pid,
            "timestamp": time.time(),
            "rounds": 0,
        }
        # 不 stop_event —— 让消息传给当前人格，由其决定是否同意

    # ── LLM 回复检测：人格同意 / 人格建议 ─────────────────

    @filter.on_llm_response()
    async def on_response(self, event, response):
        umo = event.unified_msg_origin
        st = self._switch_state.get(umo)
        if not st:
            return

        response_text = _extract_response_text(response)
        if not response_text:
            return

        if st["state"] == AWAITING_PERSONA_CONSENT:
            if self._check_persona_consent(
                response_text,
                st.get("trigger_pid", ""),
                st["target_pid"],
            ):
                await self._execute_switch(
                    umo, st["target_pid"], event,
                    response_text=response_text,
                )
                self._switch_state.pop(umo, None)
                return
            st["rounds"] = st.get("rounds", 0) + 1
            if st["rounds"] >= self.config.get("consent_timeout_rounds", 3):
                self._switch_state.pop(umo, None)
            return

        if st["state"] == IDLE or st is None:
            # 检测人格是否主动提议切换
            result = self._check_persona_suggest(response_text, umo)
            if result:
                self._switch_state[umo] = {
                    "state": AWAITING_USER_CONSENT,
                    "target_pid": result,
                    "timestamp": time.time(),
                }

    # ── 切换执行 ────────────────────────────────────────

    async def _execute_switch(
        self, umo: str, target_pid: str, event,
        trigger_msg: str = "",
        response_text: str = "",
    ):
        # 持久化当前会话
        old_pid = await self._resolve_current_persona_id(event)
        if old_pid:
            old_cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if old_cid:
                m = self._conv_map.setdefault(umo, {})
                m[old_pid] = old_cid

        # 加载/创建目标人格会话
        m = self._conv_map.setdefault(umo, {})
        if target_pid in m:
            target_cid = m[target_pid]
            # TODO: AstrBot 需要支持 by-id 切换 conversation
            # 目前通过更新当前 conversation 的 persona_id 实现
            await self.context.conversation_manager.update_conversation_persona_id(
                umo, target_pid,
            )
        else:
            plat_id = event.get_platform_name() or event.get_platform_id()
            target_cid = await self.context.conversation_manager.new_conversation(
                umo, plat_id or "", persona_id=target_pid,
            )
            m[target_pid] = target_cid
            await self.context.conversation_manager.update_conversation_persona_id(
                umo, target_pid,
            )

        # 过渡文字
        pdef = self._find_persona(target_pid) or {}
        trans = pdef.get("transition_in", "")
        display = pdef.get("display_name", target_pid)

        result_msg = f"已切换至 {display}。"
        if trans:
            result_msg = f"{trans}\n{result_msg}"

        if trigger_msg and response_text:
            pass  # 人格已回复，不再阻拦

        event.set_result(MessageEventResult().message(result_msg))
        self._last_active[umo] = (target_pid, time.time())

    # ── 空闲超时 ────────────────────────────────────────

    async def _check_idle_timeout(self, umo: str, event):
        timeout_min = self.config.get("idle_timeout_minutes", 30)
        if timeout_min <= 0:
            return

        now = time.time()
        last = self._last_active.get(umo)
        if last:
            _, ts = last
            if now - ts < timeout_min * 60:
                self._last_active[umo] = (last[0], now)
                return

        # 超时 → 权重随机
        rolls = []
        for pdef in self.config.get("personas", []):
            pid = pdef.get("persona_id", "")
            w = pdef.get("weight", 0)
            if w > 0 and pid:
                rolls.append((pid, w))

        if not rolls:
            self._last_active[umo] = ("xiaoye", now)
            return

        total = sum(w for _, w in rolls)
        r = random.randint(1, total)
        acc = 0
        chosen = rolls[0][0]
        for pid, w in rolls:
            acc += w
            if r <= acc:
                chosen = pid
                break

        current_pid = await self._resolve_current_persona_id(event)
        if current_pid and current_pid == chosen:
            self._last_active[umo] = (chosen, now)
            return

        await self._execute_switch(umo, chosen, event)
        self._last_active[umo] = (chosen, now)

    # ── 检测函数 ────────────────────────────────────────

    def _match_trigger(self, msg: str) -> str | None:
        for rule in self.config.get("trigger_map", []):
            pattern = rule.get("regex", "")
            if pattern and re.search(pattern, msg):
                return rule.get("persona_id")
        return None

    def _is_user_consent(self, msg: str) -> bool:
        phrases = self.config.get("user_consent_phrases", [])
        for ph in phrases:
            if ph in msg:
                return True
        return self._match_trigger(msg) is not None

    def _check_persona_consent(
        self, text: str, current_pid: str, target_pid: str,
    ) -> bool:
        pdef = self._find_persona(current_pid) or {}
        phrases = pdef.get("consent_phrases", [])
        # 同时检查目标人格的 consent_phrases（双向）
        tpdef = self._find_persona(target_pid) or {}
        phrases.extend(tpdef.get("consent_phrases", []))
        for ph in phrases:
            if ph in text:
                return True
        return False

    def _check_persona_suggest(self, text: str, umo: str) -> str | None:
        current_pid = self._last_active.get(umo, ("", 0))[0]
        if not current_pid:
            return None
        pdef = self._find_persona(current_pid) or {}
        phrases = pdef.get("suggest_phrases", [])
        for ph in phrases:
            if ph in text:
                if "Q" in ph:
                    return "q_tech"
                if "观" in ph:
                    return "guan_philosophy"
                if "小叶" in ph:
                    return "xiaoye"
        return None

    # ── 辅助函数 ────────────────────────────────────────

    async def _resolve_current_persona_id(self, event) -> str:
        umo = event.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            return self.config.get("default_persona_id", "xiaoye")
        conv = await self.context.conversation_manager.get_conversation(umo, cid)
        return (conv and conv.persona_id) or self.config.get("default_persona_id", "xiaoye")

    def _find_persona(self, persona_id: str) -> dict | None:
        for p in self.config.get("personas", []):
            if p.get("persona_id") == persona_id:
                return p
        return None
