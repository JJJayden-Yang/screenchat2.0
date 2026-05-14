import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class CoachingState(str, Enum):
    ON_TRACK = "on_track"
    DISTRACTED = "distracted"
    STUCK = "stuck"
    MILESTONE = "milestone"
    UNCLEAR = "unclear"
    IDLE = "idle"


class CoachingIntensity(str, Enum):
    LIGHT = "轻"
    STANDARD = "标准"
    STRICT = "严格"


@dataclass(frozen=True)
class IntensityRule:
    distracted_after: timedelta
    stuck_after: timedelta
    max_reminders: int


INTENSITY_RULES = {
    CoachingIntensity.LIGHT: IntensityRule(
        distracted_after=timedelta(minutes=10),
        stuck_after=timedelta(minutes=15),
        max_reminders=2,
    ),
    CoachingIntensity.STANDARD: IntensityRule(
        distracted_after=timedelta(minutes=6),
        stuck_after=timedelta(minutes=10),
        max_reminders=4,
    ),
    CoachingIntensity.STRICT: IntensityRule(
        distracted_after=timedelta(minutes=3),
        stuck_after=timedelta(minutes=6),
        max_reminders=8,
    ),
}

CHECK_BACKOFF_STEPS = {
    CoachingIntensity.LIGHT: (120, 300, 600, 900),
    CoachingIntensity.STANDARD: (60, 120, 240, 480, 900),
    CoachingIntensity.STRICT: (60, 120, 240, 480),
}

IDLE_CHECK_INTERVAL_SECONDS = 60
IDLE_REMINDER_AFTER = {
    CoachingIntensity.LIGHT: timedelta(minutes=8),
    CoachingIntensity.STANDARD: timedelta(minutes=5),
    CoachingIntensity.STRICT: timedelta(minutes=3),
}
IDLE_REMINDER_REPEAT_AFTER = timedelta(minutes=3)


@dataclass
class CoachingSession:
    goal: str
    goal_type: str
    duration_minutes: int
    intensity: CoachingIntensity
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reminder_count: int = 0
    check_interval_seconds: int = 60
    pause_count: int = 0
    paused_until: datetime | None = None
    total_paused: timedelta = field(default_factory=timedelta)
    last_state: CoachingState = CoachingState.UNCLEAR
    state_started_at: datetime | None = None
    last_reminders: list[str] = field(default_factory=list)
    state_log: list[tuple[datetime, CoachingState, str]] = field(default_factory=list)
    last_screen_changed_at: datetime | None = None
    still_started_at: datetime | None = None
    still_seconds: int = 0
    total_idle_seconds: int = 0
    last_idle_reminder_at: datetime | None = None

    def __post_init__(self):
        if isinstance(self.intensity, str):
            self.intensity = parse_intensity(self.intensity)
        self.check_interval_seconds = CHECK_BACKOFF_STEPS[self.intensity][0]
        if self.state_started_at is None:
            self.state_started_at = self.started_at
        if self.last_screen_changed_at is None:
            self.last_screen_changed_at = self.started_at

    @property
    def ends_at(self) -> datetime:
        return self.started_at + timedelta(minutes=self.duration_minutes) + self.total_paused

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.ends_at

    def remaining_seconds(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        return max(0, int((self.ends_at - now).total_seconds()))

    def is_paused(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.paused_until is None:
            return False
        if now >= self.paused_until:
            self.resume(self.paused_until)
            return False
        return True

    def pause(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.pause_count >= 2 or self.is_paused(now):
            return False
        self.pause_count += 1
        self.paused_until = now + timedelta(minutes=2)
        self.total_paused += timedelta(minutes=2)
        return True

    def resume(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        if self.paused_until and now < self.paused_until:
            unused = self.paused_until - now
            self.total_paused -= unused
        self.paused_until = None

    def update_state(self, state: CoachingState, now: datetime, summary: str = ""):
        if state != self.last_state:
            self.last_state = state
            self.state_started_at = now
        self.state_log.append((now, state, summary))

    def record_screen_change(self, now: datetime):
        self.last_screen_changed_at = now
        self.still_started_at = None
        self.still_seconds = 0

    def record_screen_still(self, now: datetime):
        if self.still_started_at is None:
            self.still_started_at = self.last_screen_changed_at or now
        previous_still_seconds = self.still_seconds
        self.still_seconds = max(
            IDLE_CHECK_INTERVAL_SECONDS,
            int((now - self.still_started_at).total_seconds()),
        )
        self.total_idle_seconds += max(0, self.still_seconds - previous_still_seconds)
        self.update_state(
            CoachingState.IDLE,
            now,
            f"屏幕连续 {max(1, self.still_seconds // 60)} 分钟未变化",
        )

    def idle_reminder_due(self, now: datetime) -> bool:
        threshold = IDLE_REMINDER_AFTER[self.intensity]
        if self.still_seconds < int(threshold.total_seconds()):
            return False
        if self.last_idle_reminder_at is None:
            return True
        return now - self.last_idle_reminder_at >= IDLE_REMINDER_REPEAT_AFTER

    def record_idle_reminder(self, now: datetime):
        self.last_idle_reminder_at = now

    def record_reminder(self, message: str):
        self.reminder_count += 1
        self.last_reminders.append(message)
        self.last_reminders = self.last_reminders[-5:]

    def advance_check_interval(self, state: CoachingState):
        self.check_interval_seconds = next_check_interval(
            self.check_interval_seconds,
            state,
            self.intensity,
        )

    def menu_summary(self, now: datetime | None = None) -> str:
        remain = self.remaining_seconds(now)
        minutes = remain // 60
        seconds = remain % 60
        goal = self.goal if len(self.goal) <= 12 else self.goal[:12] + "..."
        return f"陪跑中：{goal} {minutes:02d}:{seconds:02d}"


@dataclass
class CoachingAnalysis:
    state: CoachingState = CoachingState.UNCLEAR
    confidence: float = 0.0
    screen_summary: str = ""
    target_relevance: str = ""
    should_interrupt: bool = False
    message: str = ""
    suggested_action: str = ""


@dataclass
class InterruptDecision:
    allowed: bool
    reason: str
    state: CoachingState


@dataclass(frozen=True)
class FocusSummary:
    goal: str
    goal_type: str
    intensity: CoachingIntensity
    planned_minutes: int
    focused_seconds: int
    pause_count: int
    paused_seconds: int
    idle_seconds: int
    ended_early: bool
    message: str
    text: str


COMPLETION_MESSAGES = (
    "完成专注，这轮很扎实。你把注意力留在了真正重要的事情上。",
    "完成专注，漂亮。稳定推进比一口气冲很远更可靠。",
    "完成专注，今天的星图又多了一颗亮星。",
)

EARLY_END_MESSAGES = (
    "没关系，这轮先停在这里也算数。已经开始、已经推进，就不是空白。",
    "没关系，提前收尾不是失败。把状态留住，下一轮会更容易接上。",
    "没关系，能意识到该停下来本身也是一种掌控感。",
)


def parse_intensity(value: str | CoachingIntensity) -> CoachingIntensity:
    if isinstance(value, CoachingIntensity):
        return value
    aliases = {
        "light": CoachingIntensity.LIGHT,
        "轻": CoachingIntensity.LIGHT,
        "standard": CoachingIntensity.STANDARD,
        "标准": CoachingIntensity.STANDARD,
        "strict": CoachingIntensity.STRICT,
        "严格": CoachingIntensity.STRICT,
    }
    return aliases.get(str(value).strip().lower(), CoachingIntensity.STANDARD)


def parse_state(value: str | CoachingState) -> CoachingState:
    if isinstance(value, CoachingState):
        return value
    try:
        return CoachingState(str(value).strip())
    except ValueError:
        return CoachingState.UNCLEAR


def next_check_interval(
    current_seconds: int,
    state: CoachingState,
    intensity: CoachingIntensity = CoachingIntensity.STANDARD,
) -> int:
    state = parse_state(state)
    intensity = parse_intensity(intensity)
    steps = CHECK_BACKOFF_STEPS[intensity]
    if state in (CoachingState.DISTRACTED, CoachingState.STUCK, CoachingState.IDLE):
        return steps[0]
    if state == CoachingState.UNCLEAR:
        return current_seconds
    try:
        index = steps.index(current_seconds)
    except ValueError:
        index = 0
        for i, value in enumerate(steps):
            if current_seconds <= value:
                index = i
                break
        else:
            index = len(steps) - 1
    return steps[min(index + 1, len(steps) - 1)]


def manual_end_notification(session: CoachingSession, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now < session.ends_at:
        return f"这轮「{session.goal}」先到这里也没关系，已经比完全没开始强很多。歇一下，下一轮再接着来。"
    return "陪跑结束，已生成本轮总结。"


def idle_reminder_message(session: CoachingSession) -> str:
    """屏幕长期不变时，提醒用户确认自己是否还在专注。"""
    idle_minutes = max(1, session.still_seconds // 60)
    return f"屏幕已经 {idle_minutes} 分钟没变化了。你还在「{session.goal}」上吗？如果只是走神或去看手机了，先把注意力拉回来。"


def _pick_message(messages: tuple[str, ...], session: CoachingSession, message_index: int | None) -> str:
    if message_index is None:
        seed = f"{session.goal}|{session.started_at.isoformat()}|{session.pause_count}"
        message_index = sum(ord(ch) for ch in seed)
    return messages[message_index % len(messages)]


def _used_pause_seconds(session: CoachingSession, now: datetime) -> int:
    paused = session.total_paused
    if session.paused_until and now < session.paused_until:
        paused -= session.paused_until - now
    return max(0, int(paused.total_seconds()))


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, second = divmod(seconds, 60)
    if minutes <= 0:
        return f"{second} 秒"
    if second == 0:
        return f"{minutes} 分钟"
    return f"{minutes} 分 {second} 秒"


def build_focus_summary(
    session: CoachingSession,
    now: datetime | None = None,
    reason: str = "manual_end",
    message_index: int | None = None,
) -> FocusSummary:
    now = now or datetime.now(timezone.utc)
    ended_early = reason != "auto_end" and now < session.ends_at
    paused_seconds = _used_pause_seconds(session, now)
    idle_seconds = max(0, int(session.total_idle_seconds or 0))
    elapsed_seconds = max(0, int((now - session.started_at).total_seconds()))
    focused_seconds = max(0, elapsed_seconds - paused_seconds - idle_seconds)
    planned_seconds = session.duration_minutes * 60
    focused_seconds = min(focused_seconds, planned_seconds)
    messages = EARLY_END_MESSAGES if ended_early else COMPLETION_MESSAGES
    message = _pick_message(messages, session, message_index)

    status = "提前结束" if ended_early else "完成专注"
    text = (
        f"{status}：{session.goal}\n"
        f"本轮专注了 {_format_duration(focused_seconds)}，计划 {session.duration_minutes} 分钟。\n"
        f"暂停 {session.pause_count} 次，共 {_format_duration(paused_seconds)}。\n"
        f"待机 {_format_duration(idle_seconds)}。\n"
        f"{message}"
    )
    return FocusSummary(
        goal=session.goal,
        goal_type=session.goal_type,
        intensity=session.intensity,
        planned_minutes=session.duration_minutes,
        focused_seconds=focused_seconds,
        pause_count=session.pause_count,
        paused_seconds=paused_seconds,
        idle_seconds=idle_seconds,
        ended_early=ended_early,
        message=message,
        text=text,
    )


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def parse_analysis(raw: str) -> CoachingAnalysis:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return CoachingAnalysis()

    state = parse_state(data.get("state", "unclear"))
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    message = str(data.get("message") or "").strip()
    suggested_action = str(data.get("suggested_action") or "").strip()
    should = bool(data.get("should_interrupt", False))

    if state == CoachingState.UNCLEAR or confidence < 0.5:
        return CoachingAnalysis(
            state=CoachingState.UNCLEAR,
            confidence=confidence,
            screen_summary=str(data.get("screen_summary") or "").strip(),
            target_relevance=str(data.get("target_relevance") or "").strip(),
        )

    return CoachingAnalysis(
        state=state,
        confidence=confidence,
        screen_summary=str(data.get("screen_summary") or "").strip(),
        target_relevance=str(data.get("target_relevance") or "").strip(),
        should_interrupt=should,
        message=message,
        suggested_action=suggested_action,
    )


def valid_action_message(message: str) -> bool:
    text = (message or "").strip()
    if len(text) < 18:
        return False
    low_value = ("哈哈", "抽象", "加油", "不错", "挺好", "可以啊")
    if any(word in text for word in low_value) and not any(
        marker in text for marker in ("目标", "相关", "不相关", "要不要", "下一步", "切回", "帮你", "先")
    ):
        return False
    has_goal_relation = any(marker in text for marker in ("目标", "相关", "不相关", "偏离", "卡住", "停了"))
    has_action = any(marker in text for marker in ("要不要", "下一步", "先", "切回", "帮你", "试试", "可以"))
    return has_goal_relation and has_action


def fallback_intervention_message(
    session: CoachingSession,
    state: CoachingState,
    screen_summary: str = "",
    target_relevance: str = "",
    suggested_action: str = "",
) -> str:
    """把结构化观察补成可弹出的行动提醒。"""
    state = parse_state(state)
    relation = target_relevance or screen_summary or "当前屏幕看起来和目标不太贴合"
    action = suggested_action or f"先切回「{session.goal}」相关页面"
    if state == CoachingState.STUCK:
        return f"我看到你像是在「{session.goal}」上卡住了：{relation}。要不要{action}？"
    if state == CoachingState.MILESTONE:
        return f"「{session.goal}」像是完成了一个节点：{relation}。下一步可以{action}。"
    return f"我看到你偏离了「{session.goal}」：{relation}。要不要{action}？"


def should_interrupt(
    session: CoachingSession,
    state: CoachingState,
    confidence: float,
    now: datetime,
    ai_should_interrupt: bool,
    message: str,
) -> InterruptDecision:
    state = parse_state(state)
    if confidence < 0.6:
        return InterruptDecision(False, "置信度过低", CoachingState.UNCLEAR)
    if state in (CoachingState.ON_TRACK, CoachingState.UNCLEAR):
        return InterruptDecision(False, "当前无需介入", state)
    if not ai_should_interrupt and state not in (CoachingState.DISTRACTED, CoachingState.STUCK, CoachingState.MILESTONE):
        return InterruptDecision(False, "AI 未建议介入", state)
    if not valid_action_message(message):
        return InterruptDecision(False, "提醒缺少行动价值", state)

    rule = INTENSITY_RULES[session.intensity]
    if state == CoachingState.MILESTONE and session.reminder_count >= rule.max_reminders:
        return InterruptDecision(False, "提醒次数已达上限", state)
    if session.reminder_count == 0 and state in (CoachingState.DISTRACTED, CoachingState.STUCK):
        return InterruptDecision(True, "首次明确偏离或卡住，允许提醒", state)

    elapsed = now - (session.state_started_at or session.started_at)
    if state == CoachingState.DISTRACTED and elapsed < rule.distracted_after:
        return InterruptDecision(False, "偏离时间未达阈值", state)
    if state == CoachingState.STUCK and elapsed < rule.stuck_after:
        return InterruptDecision(False, "卡住时间未达阈值", state)

    return InterruptDecision(True, "允许提醒", state)


def build_prompt(session: CoachingSession) -> str:
    type_guidance = {
        "写代码/修 bug": "重点看 IDE、终端、报错、测试结果、文档和提交状态。",
        "学习/看文档": "重点看文档、PDF、笔记、搜索和总结行为是否推进目标。",
        "防走神": "重点识别视频、社交媒体、购物、无关网页和频繁切换。",
        "自定义": "根据用户目标判断屏幕是否相关，不确定就返回 unclear。",
    }
    guidance = type_guidance.get(session.goal_type, type_guidance["自定义"])
    recent = "\n".join(f"- {item}" for item in session.last_reminders[-3:]) or "无"
    return (
        "你是「小幕」，一个目标陪跑器，不是屏幕评论员。\n"
        "你的任务是判断用户是否正在推进本轮目标，只在偏离、卡住或完成节点时给出有行动价值的提醒。\n\n"
        f"本轮目标：{session.goal}\n"
        f"目标类型：{session.goal_type}\n"
        f"陪跑强度：{session.intensity.value}\n"
        f"当前状态：{session.last_state.value}\n"
        f"最近提醒：\n{recent}\n\n"
        f"目标类型判断提示：{guidance}\n\n"
        "状态定义：\n"
        "- on_track：屏幕与目标相关，用户正在推进，必须沉默。\n"
        "- distracted：屏幕明显偏离目标。\n"
        "- stuck：屏幕与目标相关，但像是在同一问题上卡住。\n"
        "- milestone：完成一个节点，适合建议下一步。\n"
        "- unclear：看不懂或不确定，必须沉默。\n\n"
        "系统可能把屏幕长期不变记录为 idle；这是系统侧判断，你不要主动返回 idle。\n\n"
        "主动消息必须同时包含：观察、和目标的关系、下一步动作。纯吐槽或泛泛鼓励必须留空。\n"
        "只回复 JSON，不要有额外内容：\n"
        '{"state":"on_track|distracted|stuck|milestone|unclear",'
        '"confidence":0.0,'
        '"screen_summary":"20字内概括当前屏幕",'
        '"target_relevance":"当前屏幕和目标的关系",'
        '"should_interrupt":false,'
        '"message":"如果需要提醒，写观察+目标关系+下一步动作，否则空字符串",'
        '"suggested_action":"下一步动作"}'
    )


def build_summary(session: CoachingSession) -> str:
    return build_focus_summary(session).text
