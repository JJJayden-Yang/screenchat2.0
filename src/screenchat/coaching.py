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


@dataclass
class CoachingSession:
    goal: str
    goal_type: str
    duration_minutes: int
    intensity: CoachingIntensity
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reminder_count: int = 0
    last_state: CoachingState = CoachingState.UNCLEAR
    state_started_at: datetime | None = None
    last_reminders: list[str] = field(default_factory=list)
    state_log: list[tuple[datetime, CoachingState, str]] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.intensity, str):
            self.intensity = parse_intensity(self.intensity)
        if self.state_started_at is None:
            self.state_started_at = self.started_at

    @property
    def ends_at(self) -> datetime:
        return self.started_at + timedelta(minutes=self.duration_minutes)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.ends_at

    def remaining_seconds(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        return max(0, int((self.ends_at - now).total_seconds()))

    def update_state(self, state: CoachingState, now: datetime, summary: str = ""):
        if state != self.last_state:
            self.last_state = state
            self.state_started_at = now
        self.state_log.append((now, state, summary))

    def record_reminder(self, message: str):
        self.reminder_count += 1
        self.last_reminders.append(message)
        self.last_reminders = self.last_reminders[-5:]

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
    if not ai_should_interrupt and state != CoachingState.MILESTONE:
        return InterruptDecision(False, "AI 未建议介入", state)
    if not valid_action_message(message):
        return InterruptDecision(False, "提醒缺少行动价值", state)

    rule = INTENSITY_RULES[session.intensity]
    if session.reminder_count >= rule.max_reminders:
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
    if not session.state_log:
        detail = "这轮没有记录到明显推进或偏离片段。"
    else:
        parts = []
        for _, state, summary in session.state_log[-6:]:
            label = state.value
            text = summary or "无截图概括"
            parts.append(f"{label}: {text}")
        detail = "；".join(parts)
    return (
        f"本轮陪跑结束：{session.goal}。\n"
        f"目标类型：{session.goal_type}，强度：{session.intensity.value}。\n"
        f"主要记录：{detail}\n"
        "下一步：挑一个最小动作继续推进，别让上下文掉线。"
    )
