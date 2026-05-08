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
