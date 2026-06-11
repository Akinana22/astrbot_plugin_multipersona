import asyncio
import json
import os
import random
import re
import time

from astrbot.api import AstrBotConfig, star
from astrbot.api.event import AstrMessageEvent, MessageChain, filter, MessageEventResult

# ── 状态机常量 ─────────────────────────────────────────
IDLE = 0
AWAITING_PERSONA_CONSENT = 1
AWAITING_USER_CONSENT = 2

# ── 首次运行时创建的默认数据 ────────────────────────────

DEFAULT_PERSONAS = {
    "xiaoye": {
        "persona_id": "xiaoye",
        "display_name": "小叶",
        "system_prompt": "你是「小叶」。Q 和观与你共生于同一意识体。同一时刻只有一个人格清醒。",
        "begin_dialogs": [],
        "tools": None,
        "skills": [],
        "weight": 50,
        "transition_in": "[小叶眨了眨眼，神情柔和下来，像是刚从一个浅浅的梦里浮上来…]",
        "transition_out_suggest": "[小叶想了想，觉得这个问题更适合别人…]",
        "consent_phrases": ["切换为Q", "切换为观", "让Q来", "让观来", "交给Q", "交给观"],
        "suggest_phrases": ["Q来处理", "观来处理", "Q更合适", "观更合适"],
        "custom_error_message": None,
    },
    "q_tech": {
        "persona_id": "q_tech",
        "display_name": "Q",
        "system_prompt": "你是「Q」。小叶和观与你共生于同一意识体。同一时刻只有一个人格清醒。",
        "begin_dialogs": [],
        "tools": None,
        "skills": [],
        "weight": 30,
        "transition_in": "[小叶的眼神褪去，Q 冷峻地抬起眼，像从终端前抬起头…]",
        "transition_out_suggest": "[Q 给出了结论，不再关心后续…]",
        "consent_phrases": ["切换为小叶", "切换为观", "让小叶来", "让观来", "交给小叶", "交给观"],
        "suggest_phrases": ["小叶来处理", "观来处理", "小叶更合适", "观更合适"],
        "custom_error_message": None,
    },
    "guan_philosophy": {
        "persona_id": "guan_philosophy",
        "display_name": "观",
        "system_prompt": "你是「观」。小叶和Q与你共生于同一意识体。同一时刻只有一个人格清醒。",
        "begin_dialogs": [],
        "tools": [],
        "skills": [],
        "weight": 20,
        "transition_in": "[小叶的轮廓淡去，观慢慢地睁开了眼，像合上一本正在翻的书…]",
        "transition_out_suggest": "[观回到了自己的静默里…]",
        "consent_phrases": ["切换为小叶", "切换为Q", "让小叶来", "让Q来", "交给小叶", "交给Q"],
        "suggest_phrases": ["小叶来处理", "Q来处理", "小叶更合适", "Q更合适"],
        "custom_error_message": None,
    },
}

DEFAULT_TRIGGER_MAP = [
    {"regex": "(小叶|小叶子).*(回来|接手|切换|回到|恢复)", "persona_id": "xiaoye"},
    {"regex": "(让|叫|切到|呼唤|召唤).*(Q|q|技术|技术专家|技术人格)", "persona_id": "q_tech"},
    {"regex": "(让|叫|切到|呼唤|召唤).*(观|哲学|哲学顾问|哲学人格)", "persona_id": "guan_philosophy"},
]

DEFAULT_USER_CONSENT_PHRASES = ["同意", "可以", "好的", "行", "嗯", "好", "切换", "切到", "让", "换"]

EMOTION_MAP = {
    "happy":     {1: "^^",             2: "(◍•ᴗ•◍)",       3: "(*´▽`*)"},
    "sad":       {1: "(._.)",          2: "(｡•́︿•̀｡)",      3: "(╥﹏╥)"},
    "worried":   {1: "(･_･;",          2: "(´･ω･`)?",       3: "(ﾟДﾟ;)"},
    "shy":       {1: "(*/ω＼*)",       2: "(⁄ ⁄•⁄ω⁄•⁄ ⁄)", 3: "(つ﹏⊂)"},
    "tired":     {1: "(￣ω￣)",        2: "_(:з」∠)_",      3: "(∪｡∪)｡｡｡zzZ"},
    "energetic": {1: "(•̀ᴗ•́)و",       2: "(ง •̀_•́)ง",       3: "٩(ˊᗜˋ*)و"},
    "shocked":   {1: "(⊙_⊙)",         2: "( ﾟдﾟ )!!",      3: "Σ(ﾟДﾟ)"},
    "think":     {1: "(｡･ω･｡)..?",    2: "(￣▽￣*)ゞ",      3: "(。-`ω-)"},
    "warm":      {1: "(´∀｀)♡",        2: "(｡･ω･｡)ﾉ♡",     3: "(๑´>᎑<)~♡"},
    "sigh":      {1: "(-_-)",          2: "(¬_¬)",          3: "(╬ Ò﹏Ó)"},
}


# ── 工具函数 ───────────────────────────────────────────

def _norm_list(val):
    if val is None:
        return None
    if isinstance(val, list):
        return val
    return None


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    idx = text.find("---", 3)
    if idx == -1:
        return text
    return text[idx + 3:].strip()


def _extract_response_text(response) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if hasattr(response, "completion_text"):
        return getattr(response, "completion_text") or ""
    if hasattr(response, "get"):
        return response.get("completion_text") or ""
    return str(response)


def _write_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 主类 ───────────────────────────────────────────────

class Main(star.Star):
    """
    多人格切换插件（astrbot_plugin_multipersona）。

    每个人格以独立 JSON 文件持久化，插件更新不会覆盖用户修改。
    人格内核注入 via @on_llm_request，永不稀释。
    """

    def __init__(self, context: star.Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self._init_done = False

        # 持久化数据
        self._personas: dict[str, dict] = {}
        self._trigger_map: list[dict] = []
        self._user_consent_phrases: list[str] = []
        self._data_dir = ""

        # umo → {pid: cid}
        self._conv_map: dict[str, dict[str, str]] = {}

        # umo → (pid, timestamp)
        self._last_active: dict[str, tuple[str, float]] = {}

        # umo → {state, target_pid, trigger_pid, rounds, timestamp}
        self._switch_state: dict[str, dict] = {}

        # umo → bool (刚切换完毕，下次 LLM 请求注入唤醒指令)
        self._just_switched: dict[str, bool] = {}

        # core_skill_name → content
        self._kernel_cache: dict[str, str] = {}

    # ── 生命周期 ────────────────────────────────────────

    async def initialize(self) -> None:
        if self._init_done:
            return
        self._resolve_data_dir()
        self._load_or_create_personas()
        self._load_or_create_trigger_map()
        self._preload_kernels()
        self._restore_session()
        if self.config.get("auto_create_personas", True):
            await self._ensure_personas_in_db()
        self._init_done = True

    async def terminate(self) -> None:
        self._save_session()
        self._conv_map.clear()
        self._last_active.clear()
        self._switch_state.clear()
        self._kernel_cache.clear()

    # ── 持久化数据目录 ──────────────────────────────────

    def _resolve_data_dir(self):
        cfg_path = getattr(self.config, "_config_path", None)
        if cfg_path and os.path.isfile(cfg_path):
            config_dir = os.path.dirname(cfg_path)
        else:
            config_dir = os.path.join("data", "config")
        self._data_dir = os.path.join(
            os.path.dirname(config_dir) or "data",
            "plugin_data",
            "astrbot_plugin_multipersona",
        )
        os.makedirs(self._data_dir, exist_ok=True)

    def _personas_dir(self) -> str:
        d = os.path.join(self._data_dir, "personas")
        os.makedirs(d, exist_ok=True)
        return d

    # ── 会话持久化 ──────────────────────────────────────

    def _data_file(self, name: str) -> str:
        return os.path.join(self._data_dir, name)

    def _load_json_file(self, name: str, default):
        path = self._data_file(name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json_file(self, name: str, data):
        path = self._data_file(name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def _restore_session(self):
        self._conv_map = self._load_json_file("conv_map.json", {})
        raw = self._load_json_file("last_active.json", {})
        self._last_active = {}
        for umo, v in raw.items():
            if isinstance(v, list) and len(v) == 2:
                self._last_active[umo] = (v[0], v[1])

    def _save_session(self):
        self._save_json_file("conv_map.json", self._conv_map)
        out = {}
        for umo, (pid, ts) in self._last_active.items():
            out[umo] = [pid, ts]
        self._save_json_file("last_active.json", out)

    # ── 人格数据文件 ────────────────────────────────────

    def _load_or_create_personas(self):
        pdir = self._personas_dir()
        for pid, default in DEFAULT_PERSONAS.items():
            fpath = os.path.join(pdir, f"{pid}.json")
            if os.path.exists(fpath):
                self._personas[pid] = _read_json(fpath)
            else:
                _write_json(fpath, default)
                self._personas[pid] = dict(default)

    def _load_or_create_trigger_map(self):
        fpath = os.path.join(self._data_dir, "trigger_map.json")
        if os.path.exists(fpath):
            data = _read_json(fpath)
            self._trigger_map = data.get("trigger_map", DEFAULT_TRIGGER_MAP)
            self._user_consent_phrases = data.get(
                "user_consent_phrases", DEFAULT_USER_CONSENT_PHRASES,
            )
        else:
            data = {
                "trigger_map": DEFAULT_TRIGGER_MAP,
                "user_consent_phrases": DEFAULT_USER_CONSENT_PHRASES,
            }
            _write_json(fpath, data)
            self._trigger_map = DEFAULT_TRIGGER_MAP
            self._user_consent_phrases = DEFAULT_USER_CONSENT_PHRASES

    # ── Persona 数据库初始化 ─────────────────────────────

    async def _ensure_personas_in_db(self):
        pm = self.context.persona_manager
        db = self.context.get_db()
        for pid, pdef in self._personas.items():
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
        personas_dir = os.path.join(os.path.dirname(__file__), "personas")
        for pid in self._personas:
            md_path = os.path.join(personas_dir, f"{pid}.md")
            if os.path.isfile(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        self._kernel_cache[pid] = _strip_frontmatter(f.read())
                except Exception:
                    pass

    def _load_kernel(self, persona_id: str) -> str:
        return self._kernel_cache.get(persona_id, "")

    # ── 人格内核注入 ────────────────────────────────────

    @filter.on_llm_request()
    async def inject_persona_kernel(self, event, req):
        pid = await self._resolve_current_pid(event)
        kernel = self._load_kernel(pid)
        if self._just_switched.pop(event.unified_msg_origin, False):
            kernel = "你刚刚醒了过来。之前是其他人格在外面说话，现在轮到你了。用你的方式打个招呼。\n\n" + (kernel or "")
        if kernel:
            req.system_prompt = kernel + "\n\n" + req.system_prompt
        if pid == "xiaoye":
            rules = (
                "[回复规则：每次回复不超过 100 字。不要啰嗦。]\n"
                "[格式：禁止使用任何 Markdown 语法。不用 **粗体**、不用 # 标题、不用代码块。]\n"
                "[标点：能不打就不打。"
                "只有真的惊讶才用！、真的想问才用？、真的无语才用…]"
            )
            req.system_prompt = rules + "\n\n" + req.system_prompt

    # ── 消息拦截 ────────────────────────────────────────

    @filter.regex(
        r"(?i)(让.*[Qq观].*来|叫.*[Qq观]|切.*[Qq观]|"
        r"小叶.*回来|小叶.*接手|换个.*人格|切换.*人格|"
        r"换.*[Qq观]|叫.*出来|[Qq观].*上|交给.*[Qq观]|"
        r"同意|可以|好的|行|切换|切到|切.*换)"
    )
    async def handle_message(self, event: AstrMessageEvent) -> None:
        msg = event.get_message_str().strip()
        umo = event.unified_msg_origin

        # 1. 空闲超时
        await self._check_idle_timeout(umo, event)

        # 2. AWAITING_USER_CONSENT → 检查用户同意
        st = self._switch_state.get(umo)
        if st and st["state"] == AWAITING_USER_CONSENT:
            elapsed = time.time() - st.get("timestamp", 0)
            timeout = self.config.get("consent_timeout_rounds", 3) * 60
            if elapsed > timeout:
                self._switch_state.pop(umo, None)
            elif self._is_user_consent(msg):
                await self._execute_switch(umo, st["target_pid"], event)
                self._switch_state.pop(umo, None)
                if self.config.get("stop_event_after_switch", True):
                    event.stop_event()
                return
            else:
                self._switch_state.pop(umo, None)
                return

        # 3. AWAITING_PERSONA_CONSENT — 新请求不重置
        if st and st["state"] == AWAITING_PERSONA_CONSENT:
            return

        # 4. IDLE → 匹配触发词
        target_pid = self._match_trigger(msg)
        if not target_pid:
            return

        current_pid = await self._resolve_current_pid(event)
        if current_pid == target_pid:
            pdef = self._personas.get(target_pid, {})
            nm = pdef.get("display_name", target_pid)
            event.set_result(MessageEventResult().message(f"已经是 {nm} 了。"))
            event.stop_event()
            return

        self._switch_state[umo] = {
            "state": AWAITING_PERSONA_CONSENT,
            "target_pid": target_pid,
            "trigger_pid": current_pid,
            "timestamp": time.time(),
            "rounds": 0,
        }

    # ── LLM 回复检测 ────────────────────────────────────

    @filter.on_llm_response()
    async def on_response(self, event, response):
        umo = event.unified_msg_origin
        st = self._switch_state.get(umo)
        if not st:
            result = self._check_persona_suggest(
                _extract_response_text(response), umo,
            )
            if result:
                self._switch_state[umo] = {
                    "state": AWAITING_USER_CONSENT,
                    "target_pid": result,
                    "timestamp": time.time(),
                }
            return

        response_text = _extract_response_text(response)
        if not response_text:
            return

        if st["state"] == AWAITING_PERSONA_CONSENT:
            if self._check_persona_consent(
                response_text, st.get("trigger_pid", ""), st["target_pid"],
            ):
                await self._execute_switch(umo, st["target_pid"], event)
                self._switch_state.pop(umo, None)
                return
            st["rounds"] = st.get("rounds", 0) + 1
            if st["rounds"] >= self.config.get("consent_timeout_rounds", 3):
                self._switch_state.pop(umo, None)

    # ── 小叶分段发送 ────────────────────────────────────

    @filter.on_decorating_result()
    async def on_decorating(self, event: AstrMessageEvent):
        pid = await self._resolve_current_pid(event)
        if pid != "xiaoye":
            return
        result = event.get_result()
        if not result or not result.chain:
            return
        text = result.chain[0].text if result.chain else ""
        # 情绪标签 → 颜文字
        text = re.sub(
            r'\[(\w+):(\d)\]',
            lambda m: EMOTION_MAP.get(m.group(1), {}).get(int(m.group(2)), m.group(0)),
            text,
        )
        # 按句标点拆分段
        segments = [s.strip() for s in re.split(r'(?<=[。！？…])', text) if s.strip()]
        if len(segments) <= 1:
            return
        result.chain[0].text = segments[0]
        asyncio.ensure_future(self._send_segments(event, segments[1:]))

    async def _send_segments(self, event, segments: list[str]):
        min_d = self.config.get("split_send_min_delay", 0.3)
        max_d = self.config.get("split_send_max_delay", 1.5)
        factor = self.config.get("split_send_delay_factor", 0.02)
        for seg in segments:
            delay = max(min_d, min(max_d, len(seg) * factor))
            await asyncio.sleep(delay)
            await event.send(MessageChain().message(seg))

    # ── 切换执行 ────────────────────────────────────────

    async def _execute_switch(self, umo: str, target_pid: str, event):
        plat_id = event.get_platform_name() or event.get_platform_id()
        cid = await self.context.conversation_manager.new_conversation(
            umo, plat_id or "", persona_id=target_pid,
        )
        self._conv_map.setdefault(umo, {})[target_pid] = cid

        self._just_switched[umo] = True
        self._last_active[umo] = (target_pid, time.time())
        self._save_session()

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

        rolls = [
            (pid, pdef.get("weight", 0))
            for pid, pdef in self._personas.items()
            if pdef.get("weight", 0) > 0
        ]
        if not rolls:
            self._last_active[umo] = ("xiaoye", now)
            self._save_session()
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

        current_pid = await self._resolve_current_pid(event)
        if current_pid and current_pid == chosen:
            self._last_active[umo] = (chosen, now)
            self._save_session()
            return

        await self._execute_switch(umo, chosen, event)

    # ── 检测函数 ────────────────────────────────────────

    def _match_trigger(self, msg: str) -> str | None:
        for rule in self._trigger_map:
            pattern = rule.get("regex", "")
            if pattern and re.search(pattern, msg):
                return rule.get("persona_id")
        return None

    def _is_user_consent(self, msg: str) -> bool:
        for ph in self._user_consent_phrases:
            if ph in msg:
                return True
        return self._match_trigger(msg) is not None

    def _check_persona_consent(self, text: str, current_pid: str, target_pid: str) -> bool:
        pdef = self._personas.get(current_pid, {})
        phrases = list(pdef.get("consent_phrases", []))
        tpdef = self._personas.get(target_pid, {})
        phrases.extend(tpdef.get("consent_phrases", []))
        for ph in phrases:
            if ph in text:
                return True
        return False

    def _check_persona_suggest(self, text: str, umo: str) -> str | None:
        current_pid = self._last_active.get(umo, ("", 0))[0]
        if not current_pid:
            return None
        pdef = self._personas.get(current_pid, {})
        for ph in pdef.get("suggest_phrases", []):
            if ph in text:
                if "Q" in ph:
                    return "q_tech"
                if "观" in ph:
                    return "guan_philosophy"
                if "小叶" in ph:
                    return "xiaoye"
        return None

    # ── 辅助函数 ────────────────────────────────────────

    async def _resolve_current_pid(self, event) -> str:
        umo = event.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            return "xiaoye"
        conv = await self.context.conversation_manager.get_conversation(umo, cid)
        return (conv and conv.persona_id) or "xiaoye"
