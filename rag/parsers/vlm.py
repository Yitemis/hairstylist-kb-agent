# -*- coding: utf-8 -*-
"""视觉大模型（VLM）内容理解：图片描述与表格结构化。

图片与表格无法直接向量化，需先转成语义化文本。本模块将这两类调用统一封装到
火山方舟（OpenAI 兼容）Chat 端点，并遵循"可选依赖、缺省降级"原则：

- 若 CHAT 模型已配置，则调用视觉模型描述图片、结构化表格；
- 若未配置或调用失败，则降级返回占位文本（图片保留 alt 描述、表格保留
  HTML/Markdown 原文），确保解析流程不中断。
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Prompt 模板：图片描述、表格结构化两类任务
# 图片描述要求覆盖用户可能的查询角度（文字、状态、步骤、标识、外观），
# 避免只给泛泛描述导致检索命中率低。业务领域词可通过环境变量补充。
# ------------------------------------------------------------------

_IMAGE_DESCRIBE_PROMPT = (
    "你是一名图片内容理解助手，输出将用于知识库检索，需覆盖用户可能的提问角度。"
    "请用简洁准确的中文描述图片，尽量包含：\n"
    "1) 图中出现的所有文字、数字、标识、按钮名称；\n"
    "2) 设备/物体的状态或所处步骤（如待机、工作、报警、第几步）；\n"
    "3) 关键的外观特征、部件名称与相对位置。\n"
    "{domain}{extra}若图片无实质内容，只回复：无内容。"
)

_TABLE_DESCRIBE_PROMPT = (
    "你是一名表格解析助手。下面是一个 HTML 表格，请理解其表头与数据关系，"
    "注意合并单元格代表的层级归属，输出一个 JSON 数组，每个元素是一行的键值"
    "对象（键为表头）。只输出被 <json_output></json_output> 包裹的 JSON，"
    "不要多余解释。\n\nHTML 表格：\n{html}"
)


def _domain_hint() -> str:
    """读取业务领域提示（可选），引导描述覆盖行业特征词。"""
    import os

    hint = os.getenv("VLM_DOMAIN_HINT", "").strip()
    return f"业务领域：{hint}。" if hint else ""


def _get_chat_client():
    """构建火山方舟 Chat 客户端（OpenAI 兼容）。未配置则返回 None。"""
    try:
        from openai import OpenAI

        from app.core.config import chat_config

        if not chat_config.is_valid:
            return None
        return OpenAI(
            api_key=chat_config.api_key,
            base_url=chat_config.base_url,
        ), chat_config.model
    except Exception as e:  # noqa: BLE001
        logger.debug("Chat 客户端不可用，VLM 降级: %s", e)
        return None


def _image_to_data_url(image: str) -> str:
    """把图片（本地路径 / URL / base64）转换为可传给 VLM 的 URL。"""
    if image.startswith(("http://", "https://", "data:")):
        return image
    p = Path(image)
    if p.exists():
        suffix = p.suffix.lower().lstrip(".") or "png"
        mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
        data = base64.b64encode(p.read_bytes()).decode()
        return f"data:image/{mime};base64,{data}"
    # 认为已是 base64 裸串
    return f"data:image/png;base64,{image}"


def describe_image(image: str, extra_hint: str = "") -> str | None:
    """调用 VLM 描述图片内容。降级时返回 None。

    Args:
        image: 图片本地路径、URL 或 base64。
        extra_hint: 附加提示（如已知的图片标题/注释）。

    Returns:
        图片的中文语义描述；无内容或降级时返回 None。
    """
    client_info = _get_chat_client()
    if client_info is None:
        return None
    client, model = client_info

    extra = f"已知信息：{extra_hint}。" if extra_hint else ""
    prompt = _IMAGE_DESCRIBE_PROMPT.format(domain=_domain_hint(), extra=extra)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": _image_to_data_url(image)}},
                ],
            }],
            timeout=60,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text or text == "无内容":
            return None
        return text
    except Exception as e:  # noqa: BLE001
        logger.warning("VLM 图片描述失败，降级: %s", e)
        return None


def structure_table(html_table: str) -> list | None:
    """调用 Chat 模型把 HTML 表格结构化为 JSON 行数据。降级返回 None。

    Args:
        html_table: HTML 表格原文。

    Returns:
        结构化行数据（list[dict]）；降级时返回 None。
    """
    client_info = _get_chat_client()
    if client_info is None:
        return None
    client, model = client_info

    prompt = _TABLE_DESCRIBE_PROMPT.format(html=html_table)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=60,
        )
        result = (resp.choices[0].message.content or "").strip()
        match = re.search(r"<json_output>(.*?)</json_output>", result, re.DOTALL)
        json_text = match.group(1).strip() if match else result
        try:
            import json_repair

            return json_repair.loads(json_text)
        except Exception:  # noqa: BLE001
            return json.loads(json_text)
    except Exception as e:  # noqa: BLE001
        logger.warning("表格结构化失败，降级: %s", e)
        return None
