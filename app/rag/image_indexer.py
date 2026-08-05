# -*- coding: utf-8 -*-
"""图片索引：从 PDF / MinerU 输出提取图片 + 多模态 embedding + 存 Milvus + DB。

复用现有 Milvus collection (hairstylist_kb)，用 category='image' 区分。
复用 ArkVisionEmbeddingModel（多模态 embedding）支持图片。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


async def embed_image(image_path: str) -> List[float]:
    """单张图片转向量（多模态 embedding）。"""
    from app.embedding import build_embedding_model
    from agentscope.message import DataBlock, Base64Source
    m = build_embedding_model()
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
    b64 = base64.b64encode(img_bytes).decode()
    resp = await m([DataBlock(source=Base64Source(data=b64, media_type=mime))])
    return resp.embeddings[0]


async def embed_images_batch(image_paths: List[str]) -> List[List[float]]:
    """批量图片 embedding。复用 build_embedding_model 的并发能力。"""
    if not image_paths:
        return []
    # build_embedding_model 内部已并发（batch_size=1, 但多协程）
    from app.embedding import build_embedding_model
    from agentscope.message import DataBlock, Base64Source
    m = build_embedding_model()
    blocks = []
    for p in image_paths:
        with open(p, "rb") as f:
            img_bytes = f.read()
        ext = Path(p).suffix.lower().lstrip(".")
        mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
        b64 = base64.b64encode(img_bytes).decode()
        blocks.append(DataBlock(source=Base64Source(data=b64, media_type=mime)))
    resp = await m(blocks)
    return resp.embeddings


def scan_images_in_dir(
    images_dir: str,
    extensions: tuple = (".jpg", ".jpeg", ".png", ".webp"),
) -> List[str]:
    """扫描目录所有图片文件。"""
    p = Path(images_dir)
    if not p.exists():
        return []
    files = []
    for ext in extensions:
        files.extend(p.glob(f"*{ext}"))
    return sorted([str(f) for f in files])


async def index_images(
    images_dir: str,
    document_id: str,
    filename: str,
    tenant_id: str = "default",
    category: str = "image",
    parent_chunk_id: Optional[str] = None,
) -> List[dict]:
    """索引目录里所有图片到 RAG。

    Returns: [{image_id, image_path, page}, ...]
    """
    paths = scan_images_in_dir(images_dir)
    if not paths:
        logger.info("No images in %s", images_dir)
        return []

    # 1. 批量 embedding
    try:
        vectors = await embed_images_batch(paths)
    except Exception as e:
        logger.exception("Image embedding failed: %s", e)
        return []

    # 2. 存 Milvus（payload 含 image_path / category=image 区分）
    from app.rag.v2_engine import get_milvus_store
    ms = await get_milvus_store()
    payloads = []
    for p in paths:
        payloads.append({
            "parent_id": parent_chunk_id or f"img_{document_id}",  # 复用 parent_id 字段
            "tenant_id": tenant_id,
            "document_id": document_id,
            "filename": filename,
            "category": category,
            "image_path": p,  # 关键：图片本地路径
        })
    ids = ms.insert(vectors, payloads)
    logger.info("Milvus insert: %d images (doc=%s)", len(ids), document_id)

    # 3. 存业务库 (image_chunks)
    from app.db.models import ImageChunk
    from app.db.session import async_session_maker
    import os as _os

    saved = []
    async with async_session_maker() as session:
        for p, vec_id, payload in zip(paths, ids, payloads):
            # 算 image_id (UUID 稳定)
            img_id = hashlib.sha1(p.encode()).hexdigest()[:32]
            # 查重
            from sqlalchemy import select
            existing = (await session.execute(
                select(ImageChunk).where(ImageChunk.image_id == img_id)
            )).scalar_one_or_none()
            if existing:
                continue
            # 取图片尺寸
            try:
                from PIL import Image
                with Image.open(p) as im:
                    w, h = im.size
            except Exception:
                w, h = None, None
            # 提取页码（如果 filename 格式是 "p001_xxx.jpg"）
            page = None
            base = _os.path.basename(p)
            if base.startswith("p") and "_" in base:
                try:
                    page = int(base[1:base.index("_")])
                except (ValueError, IndexError):
                    pass
            session.add(ImageChunk(
                image_id=img_id,
                tenant_id=tenant_id,
                document_id=document_id,
                parent_chunk_id=parent_chunk_id,
                filename=filename,
                image_path=p,
                page=page,
                width=w,
                height=h,
                category=category,
            ))
            saved.append({"image_id": img_id, "image_path": p, "page": page})
        await session.commit()
    logger.info("ImageChunk saved: %d (doc=%s)", len(saved), document_id)
    return saved


async def search_images(
    query: str,
    tenant_id: str = "default",
    top_k: int = 5,
    document_id_filter: Optional[str] = None,
) -> List[dict]:
    """图片检索：query embedding 找相关图片。

    Returns: [{image_id, image_path, filename, page, score}, ...]
    """
    from app.rag.v2_engine import _get_embedding
    from app.rag.milvus_store import CATEGORY_KEY as _C
    from app.db.models import ImageChunk
    from app.db.session import async_session_maker
    from sqlalchemy import select

    # 1. query embedding
    query_vec = (await _get_embedding([query]))[0]

    # 2. Milvus 搜索（带 category="image" filter）— 用原始 client.search 避免 image_path schema 缺失
    from pymilvus import MilvusClient
    client = MilvusClient(uri="http://localhost:19530")
    # 构造 filter（与 MilvusStore.search 一致）
    filter_parts = [f'tenant_id == "{tenant_id}"', 'category == "image"']
    if document_id_filter:
        filter_parts.append(f'document_id == "{document_id_filter}"')
    filter_expr = " and ".join(filter_parts)
    try:
        raw_hits = client.search(
            collection_name="hairstylist_kb",
            data=[query_vec],
            limit=top_k,
            filter=filter_expr,
            output_fields=["id", "document_id", "filename", "parent_id", "tenant_id", "category"],
        )
    except Exception as e:
        logger.warning("Milvus image search failed: %s", e)
        return []
    if not raw_hits or not raw_hits[0]:
        return []

    # 3. 批量查 image_chunks 拿元信息
    document_ids = list({h.get("document_id") for h in raw_hits[0] if h.get("document_id")})
    async with async_session_maker() as session:
        stmt = select(ImageChunk).where(
            ImageChunk.tenant_id == tenant_id,
            ImageChunk.document_id.in_(document_ids) if document_ids else ImageChunk.tenant_id == tenant_id,
        )
        rows = (await session.execute(stmt)).scalars().all()
    by_doc_page = {(r.document_id, r.page): r for r in rows}
    # 没有 page 信息时退化为按 document_id
    by_doc = {}
    for r in rows:
        by_doc.setdefault(r.document_id, r)

    # 4. 拼结果（按 Milvus hit 顺序，取每条对应的 image_chunks）
    results = []
    for h in raw_hits[0]:
        doc_id = h.get("document_id", "")
        # 按 document_id 取第一个匹配的图片（page 不匹配）
        r = by_doc.get(doc_id)
        if r is None:
            continue
        results.append({
            "image_id": r.image_id,
            "image_path": r.image_path,
            "filename": r.filename,
            "page": r.page,
            "width": r.width,
            "height": r.height,
            "score": h.get("distance", 0.0),
        })
    return results
