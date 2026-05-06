from dataclasses import dataclass


@dataclass
class Conversation:
    date: str
    screen_summary: str
    comment: str
    category: str
    created_at: str
    role: str = "assistant"
