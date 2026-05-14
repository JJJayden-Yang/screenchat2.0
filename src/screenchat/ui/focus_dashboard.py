import base64
import json
import mimetypes
import os
import re
import urllib.request
import webbrowser
from datetime import datetime, timezone
from html import escape

from screenchat.memory.models import Conversation

DASHBOARD_PATH = os.path.expanduser("~/.screenchat/focus_dashboard.html")
TEXTURE_DIR_NAME = "focus_dashboard_assets"

GOAL_COLORS = {
    "写代码/修 bug": "#6ee7ff",
    "学习/看文档": "#ffd166",
    "防走神": "#ff5c8a",
    "自定义": "#b8ff7a",
}

RARITY_LABELS = {
    1: "N",
    2: "R",
    3: "SR",
    4: "SSR",
}

CELESTIAL_CATALOG = [
    {
        "name": "地球",
        "kind": "类地行星",
        "rarity": 1,
        "color": "#5fb7ff",
        "accent": "#67e8a5",
        "surface": "ocean",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/ear0xuu2.jpg",
        "companion": {"name": "月球", "kind": "天然卫星", "color": "#d8dde7"},
        "fact": "地球是目前已知唯一拥有稳定表面液态水和生命的行星，月球稳定了它的自转轴。",
    },
    {
        "name": "火星",
        "kind": "类地行星",
        "rarity": 1,
        "color": "#c7603d",
        "accent": "#f3a15d",
        "surface": "rocky",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/mar0kuu2.jpg",
        "source_note": "JPL/Caltech/USGS Viking 影像拼接全球图。",
        "companion": {"name": "火卫一", "kind": "小卫星", "color": "#a89b8e"},
        "fact": "火星有铁氧化物覆盖的红色表面，也保存着古老流水活动的地貌线索。",
    },
    {
        "name": "金星",
        "kind": "类地行星",
        "rarity": 1,
        "color": "#e5b56c",
        "accent": "#fff0b8",
        "surface": "cloud",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/ven0aaa2.jpg",
        "source_note": "JPL/Caltech Magellan 雷达影像拼接图。",
        "companion": None,
        "fact": "金星拥有极厚的二氧化碳大气，温室效应让它比更靠近太阳的水星还热。",
    },
    {
        "name": "谷神星",
        "kind": "矮行星",
        "rarity": 1,
        "color": "#9da3a7",
        "accent": "#e9f0f3",
        "surface": "crater",
        "companion": None,
        "fact": "谷神星位于火星和木星之间的小行星带，是第一颗被航天器造访的矮行星。",
    },
    {
        "name": "木星",
        "kind": "气态巨行星",
        "rarity": 2,
        "color": "#d59b65",
        "accent": "#fff1cc",
        "surface": "banded",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/jup0vss1.jpg",
        "source_note": "JPL/Caltech Voyager 影像生成的代表性木星贴图。",
        "companion": {"name": "欧罗巴", "kind": "冰海卫星", "color": "#dbeafe"},
        "fact": "木星是太阳系最大的行星，强大的引力塑造了许多卫星和小天体轨道。",
    },
    {
        "name": "土星",
        "kind": "气态巨行星",
        "rarity": 2,
        "color": "#d8c07a",
        "accent": "#fff4c4",
        "surface": "banded",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/sat0fds1.jpg",
        "source_note": "JPL/Caltech 土星代表性贴图，实际云带会随时间变化。",
        "companion": {"name": "泰坦", "kind": "厚大气卫星", "color": "#d49d4a"},
        "fact": "土星以明亮环系闻名，泰坦是太阳系中少数拥有浓厚大气的卫星。",
    },
    {
        "name": "海王星",
        "kind": "冰巨行星",
        "rarity": 2,
        "color": "#3c70ff",
        "accent": "#9be7ff",
        "surface": "storm",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/nep0fds1.jpg",
        "source_note": "JPL/Caltech 海王星代表性云带贴图。",
        "companion": {"name": "海卫一", "kind": "逆行卫星", "color": "#c9e7ff"},
        "fact": "海王星是冰巨行星，拥有高速大气风暴，海卫一可能是被捕获的柯伊伯带天体。",
    },
    {
        "name": "冥王星",
        "kind": "矮行星",
        "rarity": 2,
        "color": "#b88a70",
        "accent": "#ffe0d0",
        "surface": "icy",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/plu0rss1.jpg",
        "source_note": "JPL/Caltech 早期冥王星代表性贴图，非现代完整实测全球图。",
        "companion": {"name": "卡戎", "kind": "大型卫星", "color": "#bfc7d5"},
        "fact": "冥王星和卡戎像双天体一样共同绕质心运动，新视野号曾拍到它的心形冰原。",
    },
    {
        "name": "欧罗巴",
        "kind": "冰海卫星",
        "rarity": 3,
        "color": "#dcecff",
        "accent": "#a86b4c",
        "surface": "ice",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/jup2vss2.jpg",
        "source_note": "JPL/Caltech/USGS 欧罗巴 Voyager 马赛克贴图。",
        "companion": None,
        "fact": "欧罗巴冰壳下可能隐藏全球海洋，是寻找太阳系潜在宜居环境的重要目标。",
    },
    {
        "name": "恩克拉多斯",
        "kind": "喷泉冰卫星",
        "rarity": 3,
        "color": "#eaf7ff",
        "accent": "#9be7ff",
        "surface": "ice",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/sat2vss2.jpg",
        "source_note": "JPL/Caltech/USGS 恩克拉多斯 Voyager 马赛克贴图。",
        "companion": None,
        "fact": "恩克拉多斯会从南极裂缝喷出水冰颗粒，暗示冰壳下存在盐水海洋。",
    },
    {
        "name": "伊奥",
        "kind": "火山卫星",
        "rarity": 3,
        "color": "#f5d24b",
        "accent": "#ff5c3d",
        "surface": "volcanic",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/jup1vss2.jpg",
        "source_note": "JPL/Caltech/USGS 伊奥 Voyager/Galileo 拼接贴图。",
        "companion": None,
        "fact": "伊奥是太阳系火山活动最强烈的天体之一，潮汐力不断挤压它的内部。",
    },
    {
        "name": "盖尼米德",
        "kind": "巨型卫星",
        "rarity": 3,
        "color": "#8d9bab",
        "accent": "#d8e2f0",
        "surface": "crater",
        "texture_url": "https://space.jpl.nasa.gov/tmaps/pix/jup3vss2.jpg",
        "source_note": "JPL/Caltech/USGS 盖尼米德 Voyager 马赛克贴图。",
        "companion": None,
        "fact": "盖尼米德是太阳系最大的卫星，也是已知唯一拥有自身磁场的卫星。",
    },
    {
        "name": "TRAPPIST-1e",
        "kind": "系外类地行星",
        "rarity": 4,
        "color": "#8fd8ff",
        "accent": "#f6d365",
        "surface": "exo",
        "companion": None,
        "fact": "TRAPPIST-1 系统拥有七颗地球大小的岩质行星，TRAPPIST-1e 常被视作宜居带候选世界。",
    },
    {
        "name": "55 Cancri e",
        "kind": "超级地球",
        "rarity": 4,
        "color": "#ffb36b",
        "accent": "#fff0c2",
        "surface": "lava",
        "companion": None,
        "fact": "55 Cancri e 是距离恒星极近的超级地球，表面环境可能极端炽热。",
    },
    {
        "name": "HD 189733 b",
        "kind": "热木星",
        "rarity": 4,
        "color": "#245dff",
        "accent": "#9be7ff",
        "surface": "storm",
        "companion": None,
        "fact": "HD 189733 b 是著名热木星，观测显示它呈深蓝色，并有极端高速风暴环境。",
    },
    {
        "name": "开普勒-186f",
        "kind": "系外类地行星",
        "rarity": 4,
        "color": "#b8ff7a",
        "accent": "#5fb7ff",
        "surface": "exo",
        "companion": None,
        "fact": "开普勒-186f 是早期发现的地球大小宜居带系外行星之一，围绕一颗红矮星运行。",
    },
]


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _week_label(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _short_summary(comment: str) -> str:
    lines = [line.strip() for line in (comment or "").splitlines() if line.strip()]
    return " ".join(lines[:4])


def _format_time(value: str) -> str:
    return _parse_datetime(value).strftime("%H:%M")


def _event_text(record: Conversation) -> str:
    if record.event_type == "start":
        return record.comment or f"开始陪跑：{record.target_goal}"
    if record.event_type == "observation":
        base = record.screen_summary or record.comment
        return base or "记录到一次屏幕观察。"
    if record.event_type == "reminder":
        if record.screen_summary and record.comment:
            return f"{record.screen_summary}。提醒：{record.comment}"
        return record.screen_summary or record.comment or "触发了一次陪跑提醒。"
    return _short_summary(record.comment) or "本轮结束。"


def _timeline_for_record(record: Conversation, all_records: list[Conversation]) -> list[dict]:
    end_at = _parse_datetime(record.created_at)
    related = [
        item for item in all_records
        if item.category == "coaching"
        and item.target_goal == record.target_goal
        and _parse_datetime(item.created_at) <= end_at
    ]
    starts = [
        item for item in related
        if item.event_type == "start" and _parse_datetime(item.created_at) <= end_at
    ]
    start_at = _parse_datetime(starts[-1].created_at) if starts else None
    if start_at:
        related = [item for item in related if _parse_datetime(item.created_at) >= start_at]
    timeline = []
    for item in sorted(related, key=lambda value: _parse_datetime(value.created_at)):
        if item.event_type not in ("start", "observation", "reminder", "auto_end", "manual_end"):
            continue
        text = _event_text(item)
        if not text:
            continue
        timeline.append({
            "time": _format_time(item.created_at),
            "state": item.coaching_state or item.event_type,
            "type": item.event_type,
            "text": text,
        })
    return timeline


def _duration_seconds_from_text(comment: str) -> int:
    match = re.search(r"本轮专注了\s*(?:(\d+)\s*分(?:钟)?)?\s*(?:(\d+)\s*秒)?", comment or "")
    if not match:
        return 0
    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2) or 0)
    return minutes * 60 + seconds


def _focused_seconds(record: Conversation) -> int:
    value = int(record.focused_seconds or 0)
    if value > 0:
        return value
    parsed = _duration_seconds_from_text(record.comment)
    if parsed > 0:
        return parsed
    if record.event_type == "auto_end" and int(record.planned_minutes or 0) > 0:
        return int(record.planned_minutes) * 60
    return 0


def _rarity_rank(focused_seconds: int, ended_early: bool) -> int:
    if focused_seconds >= 75 * 60 and not ended_early:
        return 4
    if focused_seconds >= 45 * 60:
        return 3
    if focused_seconds >= 25 * 60:
        return 2
    return 1


def _unlock_celestial(index: int, focused_seconds: int, ended_early: bool, used_names: set[str] | None = None) -> dict:
    rank = _rarity_rank(focused_seconds, ended_early)
    used_names = used_names or set()
    candidates = [item for item in CELESTIAL_CATALOG if item["rarity"] == rank]
    fresh_candidates = [item for item in candidates if item["name"] not in used_names]
    if fresh_candidates:
        candidates = fresh_candidates
    elif len(used_names) < len(CELESTIAL_CATALOG):
        candidates = [item for item in CELESTIAL_CATALOG if item["name"] not in used_names]
    if not candidates:
        candidates = CELESTIAL_CATALOG
    item = candidates[index % len(candidates)]
    return dict(item)


def _star_from_record(
    record: Conversation,
    index: int,
    used_names: set[str] | None = None,
    timeline: list[dict] | None = None,
) -> dict:
    created_at = _parse_datetime(record.created_at)
    focused_seconds = _focused_seconds(record)
    focused_minutes = round(focused_seconds / 60, 1)
    goal_type = record.goal_type or "自定义"
    completed_ratio = min(1.0, focused_seconds / max(1, int(record.planned_minutes or 1) * 60))
    brightness = max(0.28, min(1.0, 0.28 + completed_ratio * 0.72))
    if bool(record.ended_early):
        brightness *= 0.62
    celestial = _unlock_celestial(index, focused_seconds, bool(record.ended_early), used_names)
    if used_names is not None:
        used_names.add(celestial["name"])
    return {
        "id": f"{created_at.date().isoformat()}-{index}",
        "goal": record.target_goal or "未命名专注",
        "goal_type": goal_type,
        "color": celestial["color"],
        "goal_color": GOAL_COLORS.get(goal_type, GOAL_COLORS["自定义"]),
        "created_at": created_at.isoformat(),
        "date": created_at.strftime("%Y-%m-%d"),
        "planned_minutes": int(record.planned_minutes or 0),
        "focused_seconds": focused_seconds,
        "focused_minutes": focused_minutes,
        "pause_count": int(record.pause_count or 0),
        "ended_early": bool(record.ended_early),
        "rarity": RARITY_LABELS[celestial["rarity"]],
        "rarity_rank": celestial["rarity"],
        "celestial": celestial,
        "brightness": round(brightness, 3),
        "size": round(0.42 + min(2.4, focused_seconds / 1800), 3),
        "summary": _short_summary(record.comment),
        "timeline": timeline or [],
    }


def build_dashboard_payload(records: list[Conversation]) -> dict:
    focus_records = [
        record for record in records
        if record.category == "coaching" and record.event_type in ("auto_end", "manual_end")
    ]
    weeks: dict[str, dict] = {}
    totals = {
        "sessions": 0,
        "focused_seconds": 0,
        "completed": 0,
        "early": 0,
        "pause_count": 0,
    }
    used_names: set[str] = set()
    for index, record in enumerate(focus_records):
        created_at = _parse_datetime(record.created_at)
        label = _week_label(created_at)
        week = weeks.setdefault(label, {"label": label, "stars": [], "focused_seconds": 0})
        star = _star_from_record(record, index, used_names, _timeline_for_record(record, records))
        week["stars"].append(star)
        week["focused_seconds"] += star["focused_seconds"]
        totals["sessions"] += 1
        totals["focused_seconds"] += star["focused_seconds"]
        totals["pause_count"] += star["pause_count"]
        if star["ended_early"]:
            totals["early"] += 1
        else:
            totals["completed"] += 1
    ordered_weeks = sorted(weeks.values(), key=lambda item: item["label"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "weeks": ordered_weeks,
    }


def _safe_texture_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", url.rsplit("/", 1)[-1] or "texture.jpg")


def _prepare_texture_assets(payload: dict, output_dir: str) -> None:
    asset_dir = os.path.join(output_dir, TEXTURE_DIR_NAME)
    os.makedirs(asset_dir, exist_ok=True)
    for week in payload.get("weeks", []):
        for star in week.get("stars", []):
            celestial = star.get("celestial", {})
            url = celestial.get("texture_url")
            if not url:
                continue
            filename = _safe_texture_name(url)
            target = os.path.join(asset_dir, filename)
            if not os.path.exists(target):
                try:
                    urllib.request.urlretrieve(url, target)
                except Exception:
                    continue
            mime_type = mimetypes.guess_type(target)[0] or "image/jpeg"
            with open(target, "rb") as fh:
                encoded = base64.b64encode(fh.read()).decode("ascii")
            celestial["texture"] = f"data:{mime_type};base64,{encoded}"


def render_dashboard_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    escaped_data = data.replace("</", "<\\/")
    title = escape("专注星图")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #030712;
      --panel: rgba(7, 13, 28, 0.66);
      --line: rgba(141, 220, 255, 0.24);
      --text: #eef8ff;
      --muted: #89a6b8;
      --accent: #78e7ff;
      --gold: #ffd166;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      overflow: hidden;
      background: radial-gradient(circle at 30% 10%, #16243e 0, #07101e 38%, #02040a 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    body.day {{
      --bg: #eaf6ff;
      --panel: rgba(244, 250, 255, 0.94);
      --line: rgba(21, 82, 128, 0.32);
      --text: #061827;
      --muted: #29485f;
      --accent: #005f9e;
      --gold: #b67b00;
      background: radial-gradient(circle at 25% 8%, #eef8ff 0, #d8eefc 34%, #a7c6d9 100%);
    }}
    #space {{
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      display: block;
    }}
    .hud {{
      position: fixed;
      inset: 0;
      pointer-events: none;
      display: grid;
      grid-template-columns: minmax(300px, 360px) 1fr minmax(300px, 380px);
      gap: 18px;
      padding: 20px;
    }}
    .panel {{
      pointer-events: auto;
      align-self: start;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, var(--panel), rgba(5, 10, 22, 0.42));
      backdrop-filter: blur(18px);
      box-shadow: 0 20px 70px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      overflow: hidden;
    }}
    body.day .panel {{
      background: linear-gradient(180deg, rgba(244, 250, 255, 0.96), rgba(220, 239, 250, 0.9));
      box-shadow: 0 18px 58px rgba(12, 49, 76, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.78);
    }}
    body.day .stat,
    body.day .info-section {{
      background: rgba(255, 255, 255, 0.42);
    }}
    body.day .mode-toggle {{
      background: rgba(230, 244, 255, 0.86);
      color: #062033;
      border-color: rgba(0, 95, 158, 0.42);
    }}
    .panel-inner {{ padding: 18px; }}
    .brand {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding: 16px 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 760;
    }}
    .subtitle {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    .mode-toggle {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.07);
      color: var(--text);
      height: 36px;
      padding: 0 12px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 700;
      white-space: nowrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 16px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.045);
      min-height: 72px;
    }}
    .stat b {{
      display: block;
      font-size: 22px;
      line-height: 1;
      color: var(--accent);
    }}
    .stat span {{
      display: block;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .legend {{
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }}
    .legend-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--muted);
      font-size: 12px;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      display: inline-block;
      border-radius: 50%;
      margin-right: 8px;
      box-shadow: 0 0 18px currentColor;
      vertical-align: -1px;
    }}
    .focus-card {{
      min-height: 260px;
      max-height: calc(100vh - 40px);
      display: flex;
      flex-direction: column;
    }}
    .right-panel .panel-inner {{
      min-height: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .focus-title {{
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .focus-goal {{
      font-size: 24px;
      line-height: 1.2;
      margin: 0 0 16px;
      font-weight: 780;
      flex: 0 0 auto;
    }}
    .details {{
      display: grid;
      gap: 10px;
      margin: 16px 0;
      flex: 0 0 auto;
    }}
    .detail {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 9px;
      color: var(--muted);
      font-size: 13px;
    }}
    .detail strong {{
      color: var(--text);
      font-weight: 720;
      text-align: right;
    }}
    .summary {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
      white-space: pre-line;
    }}
    .info-section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.045);
      margin-top: 12px;
      flex: 0 0 auto;
    }}
    .timeline-section {{
      min-height: 0;
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
    }}
    .timeline {{
      display: grid;
      gap: 9px;
      max-height: clamp(150px, 24vh, 280px);
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-right: 8px;
      scrollbar-width: thin;
      scrollbar-color: var(--accent) rgba(140, 170, 190, 0.18);
    }}
    .timeline::-webkit-scrollbar {{
      width: 6px;
    }}
    .timeline::-webkit-scrollbar-track {{
      background: rgba(140, 170, 190, 0.14);
      border-radius: 999px;
    }}
    .timeline::-webkit-scrollbar-thumb {{
      background: linear-gradient(180deg, var(--accent), var(--gold));
      border-radius: 999px;
    }}
    .timeline-row {{
      display: grid;
      grid-template-columns: 44px 1fr;
      gap: 10px;
      align-items: start;
    }}
    .timeline-time {{
      color: var(--accent);
      font-weight: 800;
      font-size: 12px;
    }}
    .timeline-text {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}
    .section-label {{
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .center-top {{
      align-self: start;
      justify-self: center;
      pointer-events: none;
      text-align: center;
      margin-top: 6px;
      text-shadow: 0 2px 18px rgba(0, 0, 0, 0.45);
    }}
    .center-top .kicker {{
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .center-top .hint {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .empty {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .week-dock {{
      pointer-events: auto;
      position: fixed;
      left: 50%;
      bottom: 18px;
      transform: translateX(-50%);
      width: min(560px, calc(100vw - 40px));
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(8, 15, 31, 0.82), rgba(4, 9, 20, 0.72));
      backdrop-filter: blur(18px);
      box-shadow: 0 18px 70px rgba(0, 0, 0, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      padding: 12px 14px 13px;
    }}
    body.day .week-dock {{
      background: linear-gradient(180deg, rgba(244, 250, 255, 0.94), rgba(219, 238, 250, 0.88));
      box-shadow: 0 18px 58px rgba(12, 49, 76, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.72);
    }}
    .week-main {{
      display: grid;
      grid-template-columns: 34px 1fr 34px;
      gap: 12px;
      align-items: center;
    }}
    .week-nav,
    .week-chip {{
      border: 1px solid var(--line);
      color: var(--text);
      background: rgba(255, 255, 255, 0.07);
      cursor: pointer;
      font-weight: 760;
      border-radius: 999px;
    }}
    .week-nav {{
      width: 34px;
      height: 34px;
      font-size: 22px;
      line-height: 1;
    }}
    .week-nav:disabled {{
      cursor: default;
      opacity: 0.36;
    }}
    .week-info {{
      min-width: 0;
    }}
    .week-title-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
      color: var(--muted);
    }}
    .week-title-row strong {{
      color: var(--text);
      font-size: 14px;
    }}
    .week-progress {{
      margin-top: 10px;
      display: grid;
      grid-template-columns: 78px 1fr;
      gap: 10px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
    }}
    .progress-track {{
      height: 7px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(140, 170, 190, 0.24);
    }}
    .progress-fill {{
      height: 100%;
      width: 0;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--gold));
      box-shadow: 0 0 18px rgba(120, 231, 255, 0.48);
    }}
    .week-tabs {{
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-top: 10px;
      scrollbar-width: none;
    }}
    .week-tabs::-webkit-scrollbar {{ display: none; }}
    .week-chip {{
      flex: 0 0 auto;
      min-width: 78px;
      height: 28px;
      padding: 0 10px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .week-chip.active {{
      color: #031018;
      border-color: rgba(120, 231, 255, 0.86);
      background: linear-gradient(90deg, #78e7ff, #ffd166);
      box-shadow: 0 0 24px rgba(120, 231, 255, 0.25);
    }}
    @media (max-width: 920px) {{
      .hud {{
        grid-template-columns: 1fr;
        align-content: start;
        overflow: auto;
        pointer-events: none;
      }}
      .panel {{
        max-width: none;
      }}
      .center-top {{ display: none; }}
      .right-panel {{ align-self: end; }}
      .week-dock {{
        bottom: 12px;
        width: calc(100vw - 24px);
      }}
    }}
  </style>
</head>
<body>
  <canvas id="space" aria-label="3D 专注星系"></canvas>
  <div class="hud">
    <section class="panel">
      <div class="brand">
        <div>
          <h1>专注星图</h1>
      <p class="subtitle">一周一个星系，每轮专注开出一个真实天体。时间越长，越容易出现稀有星球、卫星和系外世界。</p>
        </div>
        <button class="mode-toggle" id="modeToggle">日间 UI</button>
      </div>
      <div class="panel-inner">
        <div class="stats">
          <div class="stat"><b id="totalHours">0h</b><span>总专注</span></div>
          <div class="stat"><b id="totalSessions">0</b><span>星体数量</span></div>
          <div class="stat"><b id="completedCount">0</b><span>完成专注</span></div>
          <div class="stat"><b id="earlyCount">0</b><span>提前结束</span></div>
        </div>
        <div class="legend" aria-label="目标类型图例">
          <div class="legend-row"><span><i class="dot" style="color:#6ee7ff;background:#6ee7ff"></i>写代码/修 bug</span><span>轨道标记</span></div>
          <div class="legend-row"><span><i class="dot" style="color:#ffd166;background:#ffd166"></i>学习/看文档</span><span>轨道标记</span></div>
          <div class="legend-row"><span><i class="dot" style="color:#ff5c8a;background:#ff5c8a"></i>防走神</span><span>轨道标记</span></div>
          <div class="legend-row"><span><i class="dot" style="color:#b8ff7a;background:#b8ff7a"></i>自定义</span><span>轨道标记</span></div>
        </div>
      </div>
    </section>
    <div class="center-top">
      <div class="kicker">背景星系已校准</div>
      <div class="hint">拖拽旋转，滚轮缩放，点击星体查看本轮总结</div>
    </div>
    <section class="panel right-panel focus-card">
      <div class="brand">
        <div>
          <h1 id="focusPanelTitle">星体详情</h1>
          <p class="subtitle" id="focusPanelSub">选择一颗专注星，查看它记录的那一轮。</p>
        </div>
      </div>
      <div class="panel-inner">
        <p class="focus-goal" id="focusGoal">等待选择</p>
        <div class="details">
          <div class="detail"><span>专注时长</span><strong id="focusDuration">--</strong></div>
          <div class="detail"><span>解锁天体</span><strong id="focusBody">--</strong></div>
          <div class="detail"><span>稀有度</span><strong id="focusRarity">--</strong></div>
          <div class="detail"><span>目标类型</span><strong id="focusType">--</strong></div>
          <div class="detail"><span>暂停次数</span><strong id="focusPause">--</strong></div>
          <div class="detail"><span>状态</span><strong id="focusStatus">--</strong></div>
        </div>
        <div class="info-section">
          <div class="section-label">天体科普</div>
          <div class="summary" id="celestialFact">选择一颗星体，查看它的真实地貌和天体信息。</div>
        </div>
        <div class="info-section timeline-section">
          <div class="section-label">本轮专注记录</div>
          <div class="timeline" id="focusTimeline">
            <div class="timeline-row">
              <span class="timeline-time">--:--</span>
              <span class="timeline-text">你的星系会随着每一轮专注慢慢成形。现在可以先转一转这片宇宙。</span>
            </div>
          </div>
        </div>
        <div class="empty" id="emptyText"></div>
      </div>
    </section>
  </div>
  <div class="week-dock" id="weekDock" aria-label="周度星系切换">
    <div class="week-main">
      <button class="week-nav" id="prevWeek" aria-label="上一周">‹</button>
      <div class="week-info">
        <div class="week-title-row">
          <strong id="activeWeekName">本周星系</strong>
          <span id="activeWeekMeta">--</span>
        </div>
        <div class="week-progress">
          <span id="weekProgressText">专注进度 0 / 10 小时</span>
          <div class="progress-track"><div class="progress-fill" id="weekProgressFill"></div></div>
        </div>
      </div>
      <button class="week-nav" id="nextWeek" aria-label="下一周">›</button>
    </div>
    <div class="week-tabs" id="weekTabs"></div>
  </div>
  <script>
    window.FOCUS_GALAXY_DATA = {escaped_data};
  </script>
  <script type="module">
    import * as THREE from "https://unpkg.com/three@0.164.1/build/three.module.js";

    const data = window.FOCUS_GALAXY_DATA;
    const canvas = document.getElementById("space");
    const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true, alpha: true }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 1);
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x02040a, 0.0026);
    const camera = new THREE.PerspectiveCamera(54, 1, 0.1, 1600);
    camera.position.set(0, 38, 132);
    const focusTarget = new THREE.Vector3(0, 4, 0);
    const cameraDirection = camera.position.clone().sub(focusTarget).normalize();
    let cameraDistance = camera.position.distanceTo(focusTarget);
    function setCameraDistance(distance) {{
      cameraDistance = Math.max(6, Math.min(620, distance));
      camera.position.copy(focusTarget).addScaledVector(cameraDirection, cameraDistance);
    }}
    function aimCamera() {{
      camera.lookAt(focusTarget);
    }}
    aimCamera();

    const root = new THREE.Group();
    root.position.y = focusTarget.y;
    scene.add(root);
    const focusObjects = [];
    const galaxyGroups = [];
    const activeGalaxyOffset = new THREE.Vector3();
    const textureLoader = new THREE.TextureLoader();
    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    let selected = null;
    let activeWeekIndex = 0;
    let targetRootPosition = new THREE.Vector3(0, focusTarget.y, 0);
    let isDragging = false;
    let lastX = 0;
    let lastY = 0;
    let autoSpin = 0.0012;

    const ambient = new THREE.AmbientLight(0xb8dcff, 0.92);
    scene.add(ambient);
    const keyLight = new THREE.PointLight(0x9fefff, 5.8, 320);
    keyLight.position.set(-22, 28, 24);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xdbeafe, 1.35);
    fillLight.position.set(18, 12, 46);
    scene.add(fillLight);
    const warmLight = new THREE.PointLight(0xffd166, 2.3, 260);
    warmLight.position.set(38, -16, -28);
    scene.add(warmLight);

    function resize() {{
      const width = window.innerWidth;
      const height = window.innerHeight;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }}
    window.addEventListener("resize", resize);
    resize();

    function hours(seconds) {{
      const value = seconds / 3600;
      return value >= 10 ? `${{value.toFixed(0)}}h` : `${{value.toFixed(1)}}h`;
    }}
    function minutes(seconds) {{
      const min = Math.round(seconds / 60);
      return `${{min}} 分钟`;
    }}
    function setText(id, text) {{
      document.getElementById(id).textContent = text;
    }}
    function setTimeline(entries) {{
      const container = document.getElementById("focusTimeline");
      container.textContent = "";
      const rows = entries && entries.length ? entries : [{{ time: "--:--", text: "这轮还没有详细屏幕记录。" }}];
      rows.forEach(entry => {{
        const row = document.createElement("div");
        row.className = "timeline-row";
        const time = document.createElement("span");
        time.className = "timeline-time";
        time.textContent = entry.time || "--:--";
        const text = document.createElement("span");
        text.className = "timeline-text";
        text.textContent = entry.text || "";
        row.append(time, text);
        container.append(row);
      }});
    }}
    function weekShortLabel(label) {{
      const match = /W(\\d+)/.exec(label || "");
      return match ? `第 ${{Number(match[1])}} 周` : label;
    }}
    setText("totalHours", hours(data.totals.focused_seconds || 0));
    setText("totalSessions", data.totals.sessions || 0);
    setText("completedCount", data.totals.completed || 0);
    setText("earlyCount", data.totals.early || 0);
    if (!data.weeks.length) {{
      setText("emptyText", "还没有专注结束记录。完成一轮陪跑后，这里会生成你的第一颗专注星。");
    }}

    function makeGlow(color, opacity, scale) {{
      const spriteCanvas = document.createElement("canvas");
      spriteCanvas.width = 128;
      spriteCanvas.height = 128;
      const ctx = spriteCanvas.getContext("2d");
      const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 60);
      gradient.addColorStop(0, color);
      gradient.addColorStop(0.22, color);
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 128, 128);
      const texture = new THREE.CanvasTexture(spriteCanvas);
      const material = new THREE.SpriteMaterial({{ map: texture, transparent: true, opacity, depthWrite: false }});
      const sprite = new THREE.Sprite(material);
      sprite.scale.setScalar(scale);
      return sprite;
    }}

    function makePlanetTexture(base, accent, seed, surface) {{
      const textureCanvas = document.createElement("canvas");
      textureCanvas.width = 256;
      textureCanvas.height = 128;
      const ctx = textureCanvas.getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, 256, 128);
      grad.addColorStop(0, base);
      grad.addColorStop(0.55, accent);
      grad.addColorStop(1, "#ffffff");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 256, 128);
      const bandCount = surface === "banded" || surface === "storm" ? 52 : 24;
      for (let i = 0; i < bandCount; i++) {{
        const y = (i * 37 + seed * 19) % 128;
        const alpha = surface === "banded" ? 0.12 : 0.08 + ((i + seed) % 4) * 0.035;
        ctx.fillStyle = i % 2 ? `rgba(255,255,255,${{alpha}})` : `rgba(0,0,0,${{alpha * 0.5}})`;
        ctx.fillRect(0, y, 256, surface === "banded" ? 2 + (i % 3) : 1 + ((i + seed) % 5));
      }}
      const craterCount = surface === "crater" || surface === "rocky" || surface === "ice" ? 78 : 38;
      for (let i = 0; i < craterCount; i++) {{
        ctx.beginPath();
        const dark = surface === "lava" || surface === "volcanic" ? "90,20,0" : "0,0,0";
        ctx.fillStyle = `rgba(${{dark}},${{0.08 + (i % 3) * 0.04}})`;
        ctx.arc((i * 47 + seed * 13) % 256, (i * 29 + seed * 7) % 128, 1 + (i % 7), 0, Math.PI * 2);
        ctx.fill();
      }}
      if (surface === "ocean") {{
        ctx.fillStyle = "rgba(72, 214, 160, 0.34)";
        for (let i = 0; i < 12; i++) {{
          ctx.beginPath();
          ctx.ellipse((i * 61 + seed * 9) % 256, (i * 31 + seed * 5) % 128, 18 + i % 9, 6 + i % 5, i, 0, Math.PI * 2);
          ctx.fill();
        }}
      }}
      if (surface === "ice") {{
        ctx.strokeStyle = "rgba(120, 70, 40, 0.42)";
        ctx.lineWidth = 1.5;
        for (let i = 0; i < 14; i++) {{
          ctx.beginPath();
          ctx.moveTo(0, (i * 17 + seed * 11) % 128);
          ctx.bezierCurveTo(64, (i * 23) % 128, 180, (i * 13 + 40) % 128, 256, (i * 29) % 128);
          ctx.stroke();
        }}
      }}
      return new THREE.CanvasTexture(textureCanvas);
    }}

    function makeReliefTexture(base, accent, seed, surface) {{
      const reliefCanvas = document.createElement("canvas");
      reliefCanvas.width = 256;
      reliefCanvas.height = 128;
      const ctx = reliefCanvas.getContext("2d");
      ctx.fillStyle = "#777";
      ctx.fillRect(0, 0, 256, 128);
      const banded = surface === "banded" || surface === "storm";
      const icy = surface === "ice" || surface === "icy";
      const volcanic = surface === "volcanic" || surface === "lava";
      if (banded) {{
        for (let i = 0; i < 42; i++) {{
          const y = (i * 11 + seed * 7) % 128;
          ctx.fillStyle = i % 2 ? "#9a9a9a" : "#565656";
          ctx.fillRect(0, y, 256, 2 + (i % 4));
        }}
      }}
      for (let i = 0; i < (banded ? 28 : 96); i++) {{
        const x = (i * 53 + seed * 23) % 256;
        const y = (i * 31 + seed * 17) % 128;
        const r = volcanic ? 2 + (i % 10) : 1 + (i % 8);
        ctx.beginPath();
        ctx.fillStyle = i % 3 === 0 ? "#aaaaaa" : "#454545";
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
        if (!banded) {{
          ctx.beginPath();
          ctx.strokeStyle = "rgba(235,235,235,0.42)";
          ctx.arc(x + 1, y - 1, r * 1.5, 0, Math.PI * 2);
          ctx.stroke();
        }}
      }}
      if (icy) {{
        ctx.strokeStyle = "rgba(245,245,245,0.8)";
        ctx.lineWidth = 2;
        for (let i = 0; i < 18; i++) {{
          ctx.beginPath();
          ctx.moveTo(0, (i * 19 + seed * 5) % 128);
          ctx.bezierCurveTo(60, (i * 29) % 128, 190, (i * 17 + 33) % 128, 256, (i * 37) % 128);
          ctx.stroke();
        }}
      }}
      const texture = new THREE.CanvasTexture(reliefCanvas);
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
      return texture;
    }}

    function makeSurfaceOverlayTexture(star, seed) {{
      const overlayCanvas = document.createElement("canvas");
      overlayCanvas.width = 512;
      overlayCanvas.height = 256;
      const ctx = overlayCanvas.getContext("2d");
      ctx.clearRect(0, 0, 512, 256);
      const surface = star.celestial.surface;
      const banded = surface === "banded" || surface === "storm";
      if (banded) {{
        for (let i = 0; i < 58; i++) {{
          const y = (i * 13 + seed * 11) % 256;
          ctx.fillStyle = i % 2 ? "rgba(255,255,255,0.18)" : "rgba(34,18,8,0.22)";
          ctx.fillRect(0, y, 512, 2 + (i % 5));
        }}
      }} else {{
        for (let i = 0; i < 90; i++) {{
          const x = (i * 97 + seed * 31) % 512;
          const y = (i * 61 + seed * 13) % 256;
          const r = 2 + (i % 12);
          ctx.beginPath();
          ctx.fillStyle = i % 2 ? "rgba(255,255,255,0.16)" : "rgba(0,0,0,0.24)";
          ctx.ellipse(x, y, r * (1.2 + (i % 5) * 0.18), r * (0.55 + (i % 4) * 0.12), i * 0.37, 0, Math.PI * 2);
          ctx.fill();
        }}
      }}
      if (surface === "ocean") {{
        ctx.fillStyle = "rgba(24,210,145,0.28)";
        for (let i = 0; i < 20; i++) {{
          ctx.beginPath();
          ctx.ellipse((i * 71 + seed * 17) % 512, (i * 39 + seed * 9) % 256, 28 + i % 18, 8 + i % 9, i, 0, Math.PI * 2);
          ctx.fill();
        }}
      }}
      if (surface === "volcanic" || surface === "lava") {{
        ctx.fillStyle = "rgba(255,95,42,0.42)";
        for (let i = 0; i < 24; i++) {{
          ctx.beginPath();
          ctx.arc((i * 83 + seed * 41) % 512, (i * 47 + seed * 19) % 256, 3 + (i % 9), 0, Math.PI * 2);
          ctx.fill();
        }}
      }}
      const texture = new THREE.CanvasTexture(overlayCanvas);
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
      return texture;
    }}

    function createSurfaceLayer(star, radius, seed) {{
      if (star.celestial.texture) {{
        return null;
      }}
      const overlay = makeSurfaceOverlayTexture(star, seed);
      const material = new THREE.MeshBasicMaterial({{
        map: overlay,
        transparent: true,
        opacity: 0.58,
        depthWrite: false,
      }});
      return new THREE.Mesh(new THREE.SphereGeometry(radius * 1.012, 72, 48), material);
    }}

    function addBackgroundStars() {{
      const count = 2400;
      const positions = new Float32Array(count * 3);
      const colors = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {{
        const radius = 120 + Math.random() * 260;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = radius * Math.cos(phi);
        positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
        const tint = 0.68 + Math.random() * 0.32;
        colors[i * 3] = tint * (0.72 + Math.random() * 0.28);
        colors[i * 3 + 1] = tint * (0.78 + Math.random() * 0.22);
        colors[i * 3 + 2] = tint;
      }}
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const material = new THREE.PointsMaterial({{ size: 0.48, vertexColors: true, transparent: true, opacity: 0.82 }});
      scene.add(new THREE.Points(geometry, material));
    }}

    function addCosmicDust() {{
      const count = 1600;
      const positions = new Float32Array(count * 3);
      const colors = new Float32Array(count * 3);
      const blue = new THREE.Color("#2dd4ff");
      const rose = new THREE.Color("#ff5c8a");
      const gold = new THREE.Color("#ffd166");
      for (let i = 0; i < count; i++) {{
        const arm = i % 5;
        const t = i / count;
        const angle = t * Math.PI * 18 + arm * 1.25;
        const radius = 18 + t * 140 + Math.random() * 12;
        positions[i * 3] = Math.cos(angle) * radius;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 18;
        positions[i * 3 + 2] = Math.sin(angle) * radius * 0.42 - 42;
        const mixed = blue.clone().lerp(i % 3 === 0 ? rose : gold, Math.random() * 0.65);
        colors[i * 3] = mixed.r;
        colors[i * 3 + 1] = mixed.g;
        colors[i * 3 + 2] = mixed.b;
      }}
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const material = new THREE.PointsMaterial({{ size: 0.18, vertexColors: true, transparent: true, opacity: 0.28, depthWrite: false }});
      scene.add(new THREE.Points(geometry, material));
    }}

    function addDistantGalaxy(x, y, z, colorA, colorB, seed) {{
      const group = new THREE.Group();
      group.position.set(x, y, z);
      group.rotation.set(seed * 0.31, seed * 0.19, seed * 0.27);
      const count = 360;
      const positions = new Float32Array(count * 3);
      const colors = new Float32Array(count * 3);
      const c1 = new THREE.Color(colorA);
      const c2 = new THREE.Color(colorB);
      for (let i = 0; i < count; i++) {{
        const arm = i % 3;
        const t = i / count;
        const angle = t * Math.PI * 9 + arm * 2.1;
        const r = 0.4 + t * 10 + Math.random() * 1.2;
        positions[i * 3] = Math.cos(angle) * r;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 1.2;
        positions[i * 3 + 2] = Math.sin(angle) * r * 0.44;
        const mixed = c1.clone().lerp(c2, Math.random());
        colors[i * 3] = mixed.r;
        colors[i * 3 + 1] = mixed.g;
        colors[i * 3 + 2] = mixed.b;
      }}
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const material = new THREE.PointsMaterial({{ size: 0.24, vertexColors: true, transparent: true, opacity: 0.58, depthWrite: false }});
      group.add(new THREE.Points(geometry, material));
      group.add(makeGlow(colorA, 0.22, 16));
      scene.add(group);
      return group;
    }}

    function addNebula() {{
      const colors = ["rgba(80,190,255,0.9)", "rgba(255,117,188,0.65)", "rgba(255,209,102,0.55)"];
      for (let i = 0; i < 9; i++) {{
        const glow = makeGlow(colors[i % colors.length], 0.12, 34 + i * 6);
        glow.position.set((Math.random() - 0.5) * 140, (Math.random() - 0.5) * 70, -70 - Math.random() * 90);
        scene.add(glow);
      }}
    }}

    function weekPattern(weekIndex) {{
      const patterns = [
        {{ name: "倾斜椭圆", orbit: "ellipse", xScale: 1.18, zScale: 0.46, tilt: 0.34, turns: 1.0 }},
        {{ name: "双环漂移", orbit: "double", xScale: 1.0, zScale: 0.64, tilt: 0.54, turns: 1.0 }},
        {{ name: "竖琴螺旋", orbit: "spiral", xScale: 1.08, zScale: 0.52, tilt: 0.72, turns: 1.42 }},
        {{ name: "远日弧线", orbit: "arc", xScale: 1.34, zScale: 0.38, tilt: 0.46, turns: 0.72 }},
      ];
      const base = patterns[weekIndex % patterns.length];
      return {{ ...base, phase: weekIndex * 0.88 }};
    }}

    function orbitPosition(pattern, starIndex, count) {{
      const t = count <= 1 ? 0.46 : Math.max(0, Math.min(1, starIndex / Math.max(1, count - 1)));
      const angle = pattern.phase + t * Math.PI * 2 * pattern.turns;
      let radius = 10 + t * 31 + Math.sin(t * Math.PI * 2 + pattern.phase) * 2.8;
      let x = Math.cos(angle) * radius * pattern.xScale;
      let z = Math.sin(angle) * radius * pattern.zScale;
      let y = Math.sin(angle * 0.7 + pattern.phase) * 3.2;
      if (pattern.orbit === "double") {{
        x = Math.sin(angle) * radius * pattern.xScale;
        z = Math.sin(angle * 2) * radius * pattern.zScale * 0.72;
        y = Math.cos(angle) * 2.6;
      }} else if (pattern.orbit === "spiral") {{
        radius = 7 + t * 38;
        x = Math.cos(angle) * radius * pattern.xScale;
        z = Math.sin(angle) * radius * pattern.zScale;
        y = (t - 0.5) * 9 + Math.sin(angle) * 1.4;
      }} else if (pattern.orbit === "arc") {{
        const arc = -0.22 * Math.PI + t * Math.PI * 1.38 + pattern.phase;
        radius = 16 + Math.sin(t * Math.PI) * 30;
        x = Math.cos(arc) * radius * pattern.xScale;
        z = Math.sin(arc) * radius * pattern.zScale;
        y = Math.sin(t * Math.PI) * 8 - 3;
      }}
      return new THREE.Vector3(x, y, z);
    }}

    function createOrbit(radius, pattern, color = 0x78e7ff, opacity = 0.22) {{
      const curve = new THREE.EllipseCurve(0, 0, radius * pattern.xScale, radius * pattern.zScale, 0, Math.PI * 2);
      const points = curve.getPoints(160);
      const geometry = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(p.x, 0, p.y)));
      const material = new THREE.LineBasicMaterial({{ color, transparent: true, opacity }});
      const orbit = new THREE.LineLoop(geometry, material);
      orbit.rotation.x = Math.PI * 0.5 + pattern.tilt;
      orbit.rotation.z = pattern.phase * 0.18;
      return orbit;
    }}

    function createMotionTrail(pattern, starIndex, count, color) {{
      const points = [];
      const start = Math.max(0, starIndex - 0.72);
      const end = Math.min(Math.max(0, count - 1), starIndex + 0.72);
      for (let i = start; i <= end; i += 0.035) {{
        points.push(orbitPosition(pattern, i, count));
      }}
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({{ color, transparent: true, opacity: 0.48 }});
      return new THREE.Line(geometry, material);
    }}

    function createGalaxyDisc(pattern, count, color) {{
      const group = new THREE.Group();
      const discColor = new THREE.Color(color);
      for (let i = 0; i < 3; i++) {{
        const orbit = createOrbit(12 + count * 5.2 + i * 5.4, pattern, discColor, 0.18 + i * 0.045);
        group.add(orbit);
      }}
      return group;
    }}

    function createGalaxyLabel(text, color) {{
      const labelCanvas = document.createElement("canvas");
      labelCanvas.width = 512;
      labelCanvas.height = 128;
      const ctx = labelCanvas.getContext("2d");
      ctx.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
      ctx.font = "700 34px system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.shadowColor = color;
      ctx.shadowBlur = 18;
      ctx.fillStyle = color;
      ctx.fillText(text, 256, 64);
      const texture = new THREE.CanvasTexture(labelCanvas);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{ map: texture, transparent: true, opacity: 0.92, depthWrite: false }}));
      sprite.scale.set(22, 5.5, 1);
      return sprite;
    }}

    function setWeekDock() {{
      const weeks = data.weeks || [];
      const week = weeks[activeWeekIndex];
      const tabs = document.getElementById("weekTabs");
      tabs.textContent = "";
      weeks.forEach((item, index) => {{
        const chip = document.createElement("button");
        chip.className = `week-chip${{index === activeWeekIndex ? " active" : ""}}`;
        chip.textContent = index === 0 ? "本周" : weekShortLabel(item.label);
        chip.addEventListener("click", () => switchWeek(index));
        tabs.append(chip);
      }});
      document.getElementById("weekDock").style.display = weeks.length ? "block" : "none";
      if (!week) return;
      const targetHours = 10;
      const focusedHours = (week.focused_seconds || 0) / 3600;
      const progress = Math.min(100, focusedHours / targetHours * 100);
      setText("activeWeekName", activeWeekIndex === 0 ? "本周星系" : `${{weekShortLabel(week.label)}}星系`);
      setText("activeWeekMeta", `${{week.label}} · ${{week.stars.length}} 颗星`);
      setText("weekProgressText", `专注进度 ${{focusedHours.toFixed(1)}} / ${{targetHours}} 小时`);
      document.getElementById("weekProgressFill").style.width = `${{progress}}%`;
      document.getElementById("prevWeek").disabled = activeWeekIndex >= weeks.length - 1;
      document.getElementById("nextWeek").disabled = activeWeekIndex <= 0;
    }}

    function switchWeek(index, starToSelect = null) {{
      const weeks = data.weeks || [];
      if (!weeks.length) return;
      activeWeekIndex = Math.max(0, Math.min(weeks.length - 1, index));
      updateRootTarget();
      setWeekDock();
      const star = starToSelect || weeks[activeWeekIndex].stars[0];
      if (star) selectStar(star);
    }}

    function updateRootTarget() {{
      const galaxy = galaxyGroups[activeWeekIndex];
      if (!galaxy) return;
      activeGalaxyOffset.copy(galaxy.position).applyEuler(root.rotation);
      targetRootPosition.set(-activeGalaxyOffset.x, focusTarget.y - activeGalaxyOffset.y, -activeGalaxyOffset.z);
    }}

    function addFocusGalaxy() {{
      const weeks = data.weeks.length ? data.weeks : [{{ label: "等待第一周", focused_seconds: 0, stars: [] }}];
      weeks.forEach((week, weekIndex) => {{
        const galaxy = new THREE.Group();
        const pattern = weekPattern(weekIndex);
        const weekAngle = weekIndex * 1.38 + 0.24;
        const weekRadius = weekIndex === 0 ? 0 : 34 + weekIndex * 28;
        galaxy.position.set(Math.cos(weekAngle) * weekRadius, (weekIndex % 2) * 7.2, Math.sin(weekAngle) * weekRadius);
        galaxy.userData.weekIndex = weekIndex;
        root.add(galaxy);
        galaxyGroups[weekIndex] = galaxy;
        const galaxyColor = weekIndex === 0 ? "#78e7ff" : (weekIndex % 2 ? "#ffd166" : "#ff75bc");
        const core = makeGlow(galaxyColor, 0.46, 10 + Math.min(18, week.stars.length * 1.7));
        galaxy.add(core);
        const label = createGalaxyLabel(`${{week.label}} · ${{pattern.name}}`, galaxyColor);
        label.position.set(0, 12 + Math.min(8, week.stars.length * 0.8), 0);
        galaxy.add(label);
        galaxy.add(createGalaxyDisc(pattern, week.stars.length, weekIndex === 0 ? 0x78e7ff : (weekIndex % 2 ? 0xffd166 : 0xff75bc)));
        week.stars.forEach((star, starIndex) => {{
          const color = new THREE.Color(star.color);
          const texture = star.celestial.texture
            ? textureLoader.load(star.celestial.texture)
            : makePlanetTexture(
                star.celestial.color,
                star.ended_early ? "#29324d" : star.celestial.accent,
                starIndex + weekIndex * 11,
                star.celestial.surface
              );
          const relief = makeReliefTexture(
            star.celestial.color,
            star.celestial.accent,
            starIndex + weekIndex * 11,
            star.celestial.surface
          );
          const material = new THREE.MeshStandardMaterial({{
            map: texture,
            color: 0xffffff,
            bumpMap: relief,
            bumpScale: star.celestial.texture ? 0.035 : 0.16,
            emissive: color,
            emissiveIntensity: 0.06,
            roughness: 0.9,
            metalness: 0.04,
          }});
          const planetRadius = star.size * 1.18;
          const geometry = new THREE.SphereGeometry(planetRadius, 72, 48);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.copy(orbitPosition(pattern, starIndex, week.stars.length));
          mesh.userData.star = star;
          mesh.userData.weekIndex = weekIndex;
          galaxy.add(mesh);
          galaxy.add(createMotionTrail(pattern, starIndex, week.stars.length, color));
          const surfaceLayer = createSurfaceLayer(star, planetRadius, starIndex + weekIndex * 11);
          if (surfaceLayer) {{
            mesh.add(surfaceLayer);
          }}
          const glow = makeGlow(star.color, 0.08 + star.brightness * 0.12, planetRadius * 3.5);
          mesh.add(glow);
          if (star.celestial.kind.includes("巨行星") || star.celestial.name === "土星") {{
            const ringGeometry = new THREE.TorusGeometry(planetRadius * 1.8, 0.022, 8, 112);
            const ringMaterial = new THREE.MeshBasicMaterial({{ color, transparent: true, opacity: star.ended_early ? 0.18 : 0.42 }});
            const ring = new THREE.Mesh(ringGeometry, ringMaterial);
            ring.rotation.x = Math.PI * 0.58;
            ring.rotation.y = Math.PI * 0.12;
            mesh.add(ring);
          }}
          if (star.celestial.companion) {{
            const moonColor = new THREE.Color(star.celestial.companion.color || "#d8dde7");
            const moon = new THREE.Mesh(
              new THREE.SphereGeometry(Math.max(0.16, planetRadius * 0.22), 24, 16),
              new THREE.MeshStandardMaterial({{ color: moonColor, bumpMap: makeReliefTexture("#888", "#ddd", starIndex + 99, "crater"), bumpScale: 0.08, roughness: 0.86, metalness: 0.02 }})
            );
            moon.position.set(planetRadius * 1.72, planetRadius * 0.26, 0);
            moon.userData.orbitRadius = planetRadius * 1.72;
            moon.userData.orbitSpeed = 0.016 + starIndex * 0.001;
            moon.userData.orbitPhase = starIndex;
            mesh.add(moon);
            const moonOrbit = new THREE.Mesh(
              new THREE.TorusGeometry(planetRadius * 1.72, 0.01, 6, 80),
              new THREE.MeshBasicMaterial({{ color: moonColor, transparent: true, opacity: 0.22 }})
            );
            moonOrbit.rotation.x = Math.PI * 0.5;
            mesh.add(moonOrbit);
          }}
          focusObjects.push(mesh);
        }});
      }});
    }}

    function selectStar(star) {{
      selected = star;
      setText("focusGoal", star.celestial.name);
      setText("focusDuration", minutes(star.focused_seconds));
      setText("focusBody", `${{star.celestial.kind}} · ${{star.goal}}`);
      setText("focusRarity", star.rarity);
      setText("focusType", star.goal_type);
      setText("focusPause", `${{star.pause_count}} 次`);
      setText("focusStatus", star.ended_early ? "提前结束" : "完成专注");
      const companion = star.celestial.companion ? ` 伴星：${{star.celestial.companion.name}}（${{star.celestial.companion.kind}}）。` : "";
      const source = star.celestial.source_note ? `\\n贴图来源：${{star.celestial.source_note}}` : "";
      setText("celestialFact", `${{star.celestial.fact}}${{companion}}${{source}}`);
      setTimeline(star.timeline && star.timeline.length ? star.timeline : [{{ time: star.date.slice(5), text: star.summary || "这颗星还没有详细总结。" }}]);
      setText("focusPanelSub", `${{star.date}} · ${{star.rarity}} · 亮度 ${{Math.round(star.brightness * 100)}}%`);
    }}

    function updatePointer(event) {{
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    }}

    canvas.addEventListener("pointerdown", event => {{
      isDragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      autoSpin = 0;
    }});
    canvas.addEventListener("pointermove", event => {{
      if (!isDragging) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      root.rotation.y += dx * 0.006;
      root.rotation.x += dy * 0.003;
      lastX = event.clientX;
      lastY = event.clientY;
    }});
    window.addEventListener("pointerup", () => {{ isDragging = false; }});
    canvas.addEventListener("wheel", event => {{
      event.preventDefault();
      setCameraDistance(cameraDistance + event.deltaY * 0.22);
      aimCamera();
    }}, {{ passive: false }});
    canvas.addEventListener("click", event => {{
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(focusObjects, false)[0];
      if (hit && hit.object.userData.star) {{
        selectStar(hit.object.userData.star);
      }}
    }});

    document.getElementById("prevWeek").addEventListener("click", () => switchWeek(activeWeekIndex + 1));
    document.getElementById("nextWeek").addEventListener("click", () => switchWeek(activeWeekIndex - 1));

    document.getElementById("modeToggle").addEventListener("click", () => {{
      document.body.classList.toggle("day");
      const day = document.body.classList.contains("day");
      document.getElementById("modeToggle").textContent = day ? "夜间 UI" : "日间 UI";
      renderer.setClearColor(0x000000, 1);
      scene.fog.color.set(0x02040a);
      ambient.intensity = day ? 0.72 : 0.92;
    }});

    addBackgroundStars();
    addCosmicDust();
    addNebula();
    addDistantGalaxy(-58, 22, -96, "#78e7ff", "#ff75bc", 1);
    addDistantGalaxy(68, -8, -120, "#ffd166", "#9be7ff", 2);
    addDistantGalaxy(18, 35, -155, "#b8ff7a", "#78e7ff", 3);
    addDistantGalaxy(-92, -24, -145, "#ff5c8a", "#ffd166", 4);
    addDistantGalaxy(102, 28, -190, "#f8fafc", "#78e7ff", 5);
    addDistantGalaxy(-124, 36, -210, "#ffd166", "#ff5c8a", 6);
    addFocusGalaxy();
    setWeekDock();
    switchWeek(0);

    function animate() {{
      requestAnimationFrame(animate);
      root.rotation.y += autoSpin;
      updateRootTarget();
      if (isDragging) {{
        root.position.copy(targetRootPosition);
      }} else {{
        root.position.lerp(targetRootPosition, 0.12);
      }}
      aimCamera();
      focusObjects.forEach((object, index) => {{
        object.rotation.y += 0.004 + index * 0.0003;
        object.rotation.x += 0.0015;
        object.children.forEach(child => {{
          if (child.userData && child.userData.orbitRadius) {{
            child.userData.orbitPhase += child.userData.orbitSpeed;
            child.position.x = Math.cos(child.userData.orbitPhase) * child.userData.orbitRadius;
            child.position.z = Math.sin(child.userData.orbitPhase) * child.userData.orbitRadius;
          }}
        }});
        const scale = selected && selected.id === object.userData.star.id ? 1.16 : 1;
        object.scale.lerp(new THREE.Vector3(scale, scale, scale), 0.08);
      }});
      renderer.render(scene, camera);
    }}
    animate();
  </script>
</body>
</html>
"""


def write_dashboard(records: list[Conversation], output_path: str | None = None) -> str:
    output_path = output_path or DASHBOARD_PATH
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = build_dashboard_payload(records)
    _prepare_texture_assets(payload, os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(render_dashboard_html(payload))
    return output_path


def open_dashboard(records: list[Conversation] | None = None) -> str:
    if records is None:
        from screenchat.memory import database

        database.init()
        records = database.get_all()
    path = write_dashboard(records)
    webbrowser.open(f"file://{path}")
    return path
