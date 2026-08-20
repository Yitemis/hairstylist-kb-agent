# -*- coding: utf-8 -*-
"""Booking 局部 ReAct 解析器.

借鉴 JavaGuide §3.5 "Context Assembler" + JavaGuide §6 工具调用：
- 每次 LLM 调用前组装上下文
- 工具描述先讲边界 + 反例
- 用 LLM 解析自然语言为结构化字段

为什么是"局部 ReAct"（不是 Agent Loop）：
- 任务非常窄：从自然语言提取结构化字段
- 不需要工具调用（LLM 自己能做）
- 不需要多轮推理
- 1 次 LLM 调用就够

这就是 JavaGuide §1.1 说的 Agentic Workflows：
"全局 Workflow（状态机）+ 局部 Agent 子循环（解析）"
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.core.model_factory import get_model
from agentscope.message import UserMsg, SystemMsg, TextBlock

logger = logging.getLogger(__name__)


# ============ 工具函数 ============

def _extract_text(resp: Any) -> str:
    """从 model 响应里提取纯文本."""
    if isinstance(resp, str):
        return resp
    if hasattr(resp, "content"):
        content = resp.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
                elif hasattr(block, "text"):
                    parts.append(block.text)
            return "".join(parts)
    return str(resp)


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 文本里抠出 JSON 对象."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ``` 块
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # 第一个 { ... } 块
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _is_null_result(parsed: Optional[dict]) -> bool:
    """判断解析结果是否为 null/空."""
    if parsed is None:
        return True
    if parsed.get("result") is None:
        return True
    return False


# ============ 1. parse_branch_choice ============

async def parse_branch_choice(
    user_input: str,
    branches: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """解析用户对分店的选择.

    Examples:
        "人民广场那家" → {"id": 2, "name": "人民广场店"}
        "换一家吧" → None（让外层路由处理回退）
        "1 号" → {"id": 1, ...}
    """
    if not user_input or not branches:
        return None

    # 数字快速匹配
    num_match = re.search(r"^[\s]*(\d+)[\s号家]*$", user_input.strip())
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(branches):
            b = branches[idx]
            return {"id": b["id"], "name": b.get("name", ""), "address": b.get("address", "")}

    # 精确/包含匹配（用户直接说店名时）
    for b in branches:
        name = b.get("name", "")
        if name and (name in user_input or user_input in name):
            return {"id": b["id"], "name": name, "address": b.get("address", "")}

    # LLM 解析
    branches_text = "\n".join(
        f"[{i+1}] id={b['id']} {b.get('name', '')}（{b.get('address', '')}）"
        for i, b in enumerate(branches)
    )

    prompt = f"""从用户输入里提取分店选择.

可选分店:
{branches_text}

用户输入: "{user_input}"

如果用户明确选了某家（包括店名、地址、数字、别名），输出 JSON:
{{"id": 数字ID, "name": "店名", "address": "地址"}}

如果用户没明确选（比如在问问题、说"换一家"、"先这样"），输出:
{{"result": null}}

只输出 JSON, 不要其他解释."""

    try:
        model = get_model("chat")
        resp = await model([
            SystemMsg(name="system", content=[TextBlock(text="你是订单解析助手，只输出 JSON。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = _extract_text(resp)
        parsed = _extract_json(text)
        if _is_null_result(parsed):
            return None
        if "id" in parsed and any(b["id"] == parsed["id"] for b in branches):
            b = next(b for b in branches if b["id"] == parsed["id"])
            return {
                "id": b["id"],
                "name": b.get("name", ""),
                "address": b.get("address", ""),
            }
    except Exception as e:
        logger.warning("parse_branch_choice failed: %s", e)

    return None


# ============ 2. parse_service_choice ============

async def parse_service_choice(
    user_input: str,
    services: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """解析用户对服务的选择."""
    if not user_input or not services:
        return None

    num_match = re.search(r"^[\s]*第?(\d+)[\s个种]*$", user_input.strip())
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(services):
            s = services[idx]
            return {"id": s["id"], "name": s.get("name", "")}

    # 精确/包含匹配
    for s in services:
        name = s.get("name", "")
        if name and (name in user_input or user_input in name):
            return {"id": s["id"], "name": name}

    services_text = "\n".join(
        f"[{i+1}] id={s['id']} {s.get('name', '')}（{s.get('duration_minutes', '?')}分钟）"
        for i, s in enumerate(services)
    )

    prompt = f"""从用户输入里提取服务项目选择.

可选服务:
{services_text}

用户输入: "{user_input}"

如果用户明确选了某个服务，输出 JSON:
{{"id": 数字ID, "name": "服务名"}}

如果用户没明确选（比如"你帮我推荐"、"不知道选什么"），输出:
{{"result": null}}

只输出 JSON, 不要其他解释."""

    try:
        model = get_model("chat")
        resp = await model([
            SystemMsg(name="system", content=[TextBlock(text="你是订单解析助手，只输出 JSON。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = _extract_text(resp)
        parsed = _extract_json(text)
        if _is_null_result(parsed):
            return None
        if "id" in parsed and any(s["id"] == parsed["id"] for s in services):
            s = next(s for s in services if s["id"] == parsed["id"])
            return {"id": s["id"], "name": s.get("name", "")}
    except Exception as e:
        logger.warning("parse_service_choice failed: %s", e)

    return None


# ============ 3. parse_stylist_choice ============

async def parse_stylist_choice(
    user_input: str,
    stylists: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """解析用户对发型师的选择."""
    if not user_input or not stylists:
        return None

    num_match = re.search(r"^[\s]*第?(\d+)[\s个位]*$", user_input.strip())
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(stylists):
            s = stylists[idx]
            return {"id": s["id"], "name": s.get("name", "")}

    # 精确/包含匹配
    for s in stylists:
        name = s.get("name", "")
        if name and (name in user_input or user_input in name):
            return {"id": s["id"], "name": name}

    stylists_text = "\n".join(
        f"[{i+1}] id={s['id']} {s.get('name', '')} {s.get('description', '')}"
        for i, s in enumerate(stylists)
    )

    prompt = f"""从用户输入里提取发型师选择.

可选发型师:
{stylists_text}

用户输入: "{user_input}"

如果用户明确选了某位，输出 JSON:
{{"id": 数字ID, "name": "姓名"}}

如果用户没明确选（比如"你推荐"、"随便"），输出:
{{"result": null}}

只输出 JSON, 不要其他解释."""

    try:
        model = get_model("chat")
        resp = await model([
            SystemMsg(name="system", content=[TextBlock(text="你是订单解析助手，只输出 JSON。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = _extract_text(resp)
        parsed = _extract_json(text)
        if _is_null_result(parsed):
            return None
        if "id" in parsed and any(s["id"] == parsed["id"] for s in stylists):
            s = next(s for s in stylists if s["id"] == parsed["id"])
            return {"id": s["id"], "name": s.get("name", "")}
    except Exception as e:
        logger.warning("parse_stylist_choice failed: %s", e)

    return None


# ============ 4. parse_datetime ============

async def parse_datetime(
    user_input: str,
    today_iso: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """解析用户给出的预约日期和时间."""
    if not user_input:
        return None

    if today_iso is None:
        today_iso = datetime.now().date().isoformat()

    # 第一关：正则快速解析
    quick = _quick_parse_datetime(user_input, today_iso)
    if quick:
        return quick

    # 第二关：LLM 解析
    today = datetime.fromisoformat(today_iso).date()
    weekday_map_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    next_days = []
    for i in range(14):
        d = today + timedelta(days=i)
        next_days.append(f"{d.isoformat()} ({weekday_map_cn[d.weekday()]})")

    prompt = f"""从用户输入里提取预约日期和时间.

今天: {today_iso} ({weekday_map_cn[today.weekday()]})
未来 14 天日期:
{chr(10).join(next_days)}

用户输入: "{user_input}"

输出 JSON:
- date: YYYY-MM-DD 格式
- time: HH:MM 格式（24 小时制，"上午 10 点" = "10:00"，"晚上 8 点" = "20:00"，"下午 3 点半" = "15:30"）

如果无法解析（比如"随便"、"以后再说"），输出:
{{"result": null}}

只输出 JSON, 不要其他解释."""

    try:
        model = get_model("chat")
        resp = await model([
            SystemMsg(name="system", content=[TextBlock(text="你是订单解析助手，只输出 JSON。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = _extract_text(resp)
        parsed = _extract_json(text)
        if _is_null_result(parsed):
            return None
        if "date" in parsed and "time" in parsed:
            try:
                d = datetime.fromisoformat(parsed["date"])
                t = datetime.strptime(parsed["time"], "%H:%M")
                target = datetime.combine(d.date(), t.time())
                if target < datetime.now():
                    logger.info("parse_datetime: time in past, ignore")
                    return None
                return {
                    "date": d.date().isoformat(),
                    "time": t.strftime("%H:%M"),
                }
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.warning("parse_datetime failed: %s", e)

    return None


def _quick_parse_datetime(user_input: str, today_iso: str) -> Optional[dict[str, str]]:
    """正则快速解析常见表达."""
    today = datetime.fromisoformat(today_iso).date()
    text = user_input.strip()

    # 1. 提取时间
    time_match = re.search(
        r"(\d{1,2})[：:](\d{1,2})|(\d{1,2})\s*[点时]\s*(半|(\d{1,2})\s*分?)?",
        text,
    )
    if not time_match:
        return None

    hour = 0
    minute = 0
    if time_match.group(1) and time_match.group(2):
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
    elif time_match.group(3):
        hour = int(time_match.group(3))
        if time_match.group(4) == "半":
            minute = 30
        elif time_match.group(5):
            minute = int(time_match.group(5))

    # 2. 处理 上午/下午
    if "下午" in text or "晚上" in text or "傍晚" in text:
        if hour < 12:
            hour += 12
    elif "上午" in text or "早上" in text or "凌晨" in text:
        if hour == 12:
            hour = 0
    elif hour < 8 and ("点" in text):
        # 没明确上下午，且 < 8 点，按下午处理
        hour += 12

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    time_str = f"{hour:02d}:{minute:02d}"

    # 3. 提取日期
    target_date = None
    if "今天" in text or "今晚" in text:
        target_date = today
    elif "明天" in text or "明日" in text or "明早" in text or "明晚" in text:
        target_date = today + timedelta(days=1)
    elif "后天" in text:
        target_date = today + timedelta(days=2)
    elif "大后天" in text:
        target_date = today + timedelta(days=3)
    elif "下周一" in text or "下礼拜一" in text:
        days_ahead = 0 - today.weekday() + 7
        if days_ahead <= 0:
            days_ahead += 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周二" in text or "下礼拜二" in text:
        days_ahead = 1 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周三" in text or "下礼拜三" in text:
        days_ahead = 2 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周四" in text or "下礼拜四" in text:
        days_ahead = 3 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周五" in text or "下礼拜五" in text:
        days_ahead = 4 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周六" in text or "下礼拜六" in text:
        days_ahead = 5 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周日" in text or "下礼拜日" in text:
        days_ahead = 6 - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
    elif "下周" in text or "下个周" in text or "下礼拜" in text:
        days_ahead = 0 - today.weekday() + 7
        if days_ahead <= 0:
            days_ahead += 7
        target_date = today + timedelta(days=days_ahead)
    else:
        # "X 月 Y 号" 格式
        date_match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = today.year
            try:
                target_date = datetime(year, month, day).date()
                if target_date < today:
                    target_date = datetime(year + 1, month, day).date()
            except ValueError:
                pass

    if target_date is None:
        # 只有时间没日期 → 默认明天
        target_date = today + timedelta(days=1)

    # 校验必须未来
    target_dt = datetime.combine(target_date, datetime.strptime(time_str, "%H:%M").time())
    if target_dt < datetime.now():
        return None

    return {
        "date": target_date.isoformat(),
        "time": time_str,
    }


# ============ 5. parse_phone ============

async def parse_phone(user_input: str) -> Optional[str]:
    """解析并校验手机号."""
    if not user_input:
        return None

    digits = re.sub(r"\D", "", user_input)
    if len(digits) == 11 and digits.startswith("1"):
        return digits

    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
        if len(digits) == 11 and digits.startswith("1"):
            return digits

    return None


# ============ 6. parse_yes_no ============

async def parse_yes_no(user_input: str) -> Optional[bool]:
    """解析用户是否确认."""
    if not user_input:
        return None

    text = user_input.strip().lower()
    yes_keywords = ["确认", "好的", "是的", "对", "可以", "ok", "yes", "y", "提交", "下单"]
    no_keywords = ["取消", "不要", "算了", "不", "no", "n", "放弃", "退"]

    if any(kw in text for kw in yes_keywords):
        return True
    if any(kw in text for kw in no_keywords):
        return False
    return None


# ============ 7. parse_intent_to_book ============

async def parse_intent_to_book(user_input: str) -> bool:
    """判断用户是否想开始预约."""
    if not user_input:
        return False

    text = user_input.strip()
    book_keywords = [
        "预约", "约", "订", "下单", "订单",
        "分店", "店", "发型师", "烫", "染", "剪",
        "做头发", "做造型", "弄头发",
        "时间", "几点", "什么时候", "明天", "今天",
    ]
    return any(kw in text for kw in book_keywords)


# ============ 8. detect_change_intent ============

async def detect_change_intent(user_input: str) -> Optional[str]:
    """判断用户是否想改前面已填的字段.

    Returns:
        要回退到的 step 名字（如 "checkin_branch"），或 None
    """
    if not user_input:
        return None

    text = user_input.strip()
    change_keywords = ["换", "改", "重新", "不是", "不对", "错了", "我想换", "我想改"]
    if not any(kw in text for kw in change_keywords):
        return None

    if "分店" in text or "店" in text:
        return "checkin_branch"
    if "项目" in text or "服务" in text or "烫" in text or "染" in text or "剪" in text:
        return "checkin_service"
    if "发型师" in text:
        return "checkin_stylist"
    if "时间" in text or "日期" in text or "几点" in text or "什么时候" in text:
        return "checkin_datetime"
    if "电话" in text or "手机" in text:
        return "checkin_phone"
    if "名字" in text or "姓名" in text:
        return "checkin_name"

    return None


__all__ = [
    "parse_branch_choice",
    "parse_service_choice",
    "parse_stylist_choice",
    "parse_datetime",
    "parse_phone",
    "parse_yes_no",
    "parse_intent_to_book",
    "detect_change_intent",
]
