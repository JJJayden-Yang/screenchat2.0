import json
import os

from dotenv import load_dotenv

SETTINGS_PATH = os.path.expanduser("~/.screenchat/settings.json")

DEFAULTS = {
    "api_key": "",
    "model": "kimi-k2.5",
    "base_url": "https://api.moonshot.ai/v1",
    "capture_interval": 20,
    "memory_maxlen": 20,
    "muted": False,
}


def _load_json():
    try:
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load() -> dict:
    """合并配置：settings.json > .env > defaults。"""
    load_dotenv()
    env = {
        "api_key": os.getenv("SCREENCHAT_OPENAI_API_KEY", ""),
        "model": os.getenv("SCREENCHAT_AGENT_MODEL", ""),
        "base_url": os.getenv("SCREENCHAT_OPENAI_BASE_URL", ""),
        "capture_interval": int(os.getenv("SCREENCHAT_CAPTURE_INTERVAL", "0") or "0") or 0,
        "memory_maxlen": int(os.getenv("SCREENCHAT_MEMORY_MAXLEN", "0") or "0") or 0,
        "muted": os.getenv("SCREENCHAT_MUTED", "").lower() in ("true", "1"),
    }
    file_cfg = _load_json()

    config = {}
    for key in DEFAULTS:
        config[key] = DEFAULTS[key]
        if env.get(key):  # .env 优先默认
            config[key] = env[key]
        if key in file_cfg and file_cfg[key]:  # settings.json 最高（非空才覆盖）
            config[key] = file_cfg[key]
    return config


def save(key: str, value):
    """保存单个配置项到 settings.json。"""
    data = _load_json()
    data[key] = value
    _save_json(data)


def get(key: str):
    """读取单个配置项（完整合并逻辑）。"""
    return load()[key]
