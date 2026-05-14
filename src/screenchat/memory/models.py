from dataclasses import dataclass


@dataclass
class Conversation:
    date: str
    screen_summary: str
    comment: str
    category: str
    created_at: str
    role: str = "assistant"
    event_type: str = "message"
    coaching_state: str = ""
    target_relevance: str = ""
    suggested_action: str = ""
    target_goal: str = ""
    goal_type: str = ""
    intensity: str = ""
    planned_minutes: int = 0
    focused_seconds: int = 0
    pause_count: int = 0
    ended_early: bool = False
