# -*- coding: utf-8 -*-
"""多模态对话：用户/商家可发图片 + 文字，AI 结合知识库回答。

场景：
- C 端用户上传自己的脸型照片 → AI 推荐发型 + 科普
- 商家上传客户照片 → AI 指导操作步骤
- 隔离：C 端知识库（"发型科普"）vs 商家知识库（"教程/操作"）

实现：
- text + image_url(image_b64) 一起送给 LLM
- LLM 看到图片 + 知识库召回的上下文
- 隔离通过 audience='user' / 'staff' 实现
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MultimodalMessage:
    """多模态消息：文字 + 图片列表。"""
    text: str
    image_paths: List[str] = field(default_factory=list)  # 本地路径
    image_b64s: List[str] = field(default_factory=list)  # 直接传 base64


def encode_image_to_b64(image_path: str) -> str:
    """本地图片 → base64 data URL。"""
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    suffix = p.suffix.lower().lstrip(".")
    mime = f"image/{'jpeg' if suffix in ('jpg', 'jpeg') else suffix}"
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def build_image_blocks(image_paths: List[str], image_b64s: List[str]) -> List[dict]:
    """构造 OpenAI 兼容的多模态 content blocks。"""
    blocks = []
    for p in image_paths:
        if os.path.exists(p):
            blocks.append({"type": "image_url", "image_url": {"url": encode_image_to_b64(p)}})
    for b64 in image_b64s:
        if b64.startswith("data:") or len(b64) > 100:
            url = b64 if b64.startswith("data:") else f"data:image/jpeg;base64,{b64}"
            blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks


def build_multimodal_messages(
    text: str,
    image_paths: List[str] = None,
    image_b64s: List[str] = None,
    knowledge_context: str = "",
    system_prompt: str = "",
) -> List[dict]:
    """构造发给 LLM 的完整 messages（OpenAI 格式）。

    Args:
        text: 用户问题
        image_paths: 本地图片路径列表
        image_b64s: base64 字符串列表
        knowledge_context: 从知识库检索的上下文
        system_prompt: 系统提示（含 audience 角色）
    """
    # System
    sys_content = system_prompt
    if knowledge_context:
        sys_content += f"\n\n# 知识库参考\n{knowledge_context}"
    messages = [{"role": "system", "content": sys_content}]

    # User: 文字 + 图片（多模态）
    content_blocks = []
    image_blocks = build_image_blocks(image_paths or [], image_b64s or [])
    content_blocks.extend(image_blocks)
    if text:
        content_blocks.append({"type": "text", "text": text})
    messages.append({"role": "user", "content": content_blocks})
    return messages


def get_audience_for_user(is_staff: bool) -> str:
    """根据 user role 决定 audience 过滤。"""
    return "staff" if is_staff else "user"


def get_system_prompt(is_staff: bool) -> str:
    """根据 role 给不同 system prompt（强化隔离）。"""
    if is_staff:
        return (
            "你是美发行业的专业培训顾问，面向商家发型师。"
            "重点回答：操作步骤、染色配方、剪发技术细节、护理注意事项。"
            "回答专业、详细、可操作。"
        )
    return (
        "你是面向 C 端用户的发型顾问。"
        "重点回答：发型推荐、脸型匹配、风格建议、护理科普。"
        "回答友好、易懂、避免技术术语。"
    )


async def multimodal_chat(
    text: str,
    image_paths: Optional[List[str]] = None,
    image_b64s: Optional[List[str]] = None,
    is_staff: bool = False,
    tenant_id: str = "default",
    session_id: Optional[str] = None,
    top_k: int = 3,
) -> dict:
    """多模态对话入口。

    Returns: {"answer": str, "sources": [...], "audience": str}
    """
    from app.rag.v2_engine import retrieve
    audience = get_audience_for_user(is_staff)
    sys_prompt = get_system_prompt(is_staff)

    # 1. RAG 检索（按 audience 隔离）
    # 商家：只看 staff 文档 + all 文档；用户：只看 user 文档 + all 文档
    audience_filter = [audience, "all"]

    # 如果有图片：先用 query text 检索相关知识（图片也参与 VLM 检索）
    retrieval_results = []
    if text:
        try:
            r = await retrieve(
                query=text, tenant_id=tenant_id, top_k=top_k,
                audience_filter=audience_filter,
            )
            retrieval_results = r.hits
        except Exception as e:
            logger.warning("RAG retrieve failed: %s", e)

    # 图片也调 RAG（找图库里相关的参考图）
    image_search_results = []
    if image_paths or image_b64s:
        try:
            from app.rag.image_indexer import search_images
            # 用图片路径作为 image 标识（实际 VLM 检索需 image embed）
            # 这里只做：text + 图片检索图
            from app.rag.v2_engine import _get_embedding  # text_embedding (硅基流动)
            from app.rag.milvus_store import CATEGORY_KEY
            from app.rag.image_indexer import _CACHE  # internal
            # 简化：用 text 当 query 搜图（实际应该是 image embed）
            if text:
                image_search_results = await search_images(
                    text, tenant_id=tenant_id, top_k=3,
                )
        except Exception as e:
            logger.warning("Image search failed: %s", e)

    # 2. 构造知识库上下文
    knowledge_parts = []
    for i, hit in enumerate(retrieval_results, 1):
        if hit.content:
            knowledge_parts.append(f"[参考资料 {i}] {hit.content[:500]}")
    for i, img in enumerate(image_search_results, 1):
        knowledge_parts.append(f"[参考图 {i}] {img.get('filename', '')} (page {img.get('page')})")
    knowledge_context = "\n\n".join(knowledge_parts) if knowledge_parts else ""

    # 3. 构造多模态 messages
    messages = build_multimodal_messages(
        text=text,
        image_paths=image_paths or [],
        image_b64s=image_b64s or [],
        knowledge_context=knowledge_context,
        system_prompt=sys_prompt,
    )

    # 4. 调 LLM
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg
    model = get_model("chat")
    # 转成 AgentScope 格式
    as_msgs = []
    for m in messages:
        if m["role"] == "system":
            as_msgs.append(UserMsg(name="system", content=[TextBlock(text=m["content"])]))
        elif m["role"] == "user":
            # 多模态：image_url + text
            content = []
            for block in m["content"]:
                if block["type"] == "text":
                    content.append(TextBlock(text=block["text"]))
                elif block["type"] == "image_url":
                    url = block["image_url"]["url"]
                    if url.startswith("data:"):
                        from agentscope.message import DataBlock, Base64Source
                        b64 = url.split(",", 1)[1]
                        mime = url.split(";")[0].split(":")[1]
                        content.append(DataBlock(source=Base64Source(data=b64, media_type=mime)))
            as_msgs.append(UserMsg(name="user", content=content))
    resp = await model(as_msgs, stream=False)
    answer = ""
    if hasattr(resp, "content") and resp.content:
        for b in resp.content:
            if hasattr(b, "text") and b.text:
                answer += b.text
    return {
        "answer": answer,
        "audience": audience,
        "sources_count": len(retrieval_results),
        "images_count": len(image_search_results),
        "knowledge_context": knowledge_context,
    }
