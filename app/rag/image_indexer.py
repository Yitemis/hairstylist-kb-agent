# -*- coding: utf-8 -*-
"""图片索引：从 PDF / MinerU 输出提取图片 + 多模态 embedding + 存 pgvector + DB。

P2-基础设施: 改造自 Milvus 版, 现在用 pgvector (单数据源).
复用 child_chunks 表, 用 category='image' 区分图片 vs 文本块.
复用 ArkVisionEmbeddingModel（多模态 embedding）支持图片.
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
    m = build_embedding_model(capability="mm_embedding")
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
    m = build_embedding_model(capability="mm_embedding")
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

    # 2. 存 pgvector (payload 含 image_path / category=image 区分)
    from app.rag.v2_engine import get_vector_store
    vs = await get_vector_store()
    payloads = []
    for p in paths:
        payloads.append({
            "parent_id": parent_chunk_id or f"img_{document_id}",  # 复用 parent_id 字段
            "tenant_id": tenant_id,
            "document_id": document_id,
            "filename": filename,
            "category": category,
            "image_path": p,  # 关键: 图片本地路径
            "content": "",  # 图片无文本
        })
    ids = await vs.insert(vectors, payloads)
    logger.info("pgvector insert: %d images (doc=%s)", len(ids), document_id)

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
    """图片检索: query embedding 找相关图片.

    Returns: [{image_id, image_path, filename, page, score}, ...]

    P2-基础设施: 改用 PgvectorStore (替代 pymilvus.MilvusClient 底层调用).
    """
    from app.rag.v2_engine import _get_embedding, get_vector_store
    from app.db.models import ImageChunk
    from app.db.session import async_session_maker
    from sqlalchemy import select

    # 1. query embedding
    query_vec = (await _get_embedding([query]))[0]

    # 2. 向量检索 (pgvector 一个 SQL 完成 category=image + tenant_id 过滤)
    vs = await get_vector_store()
    try:
        raw_hits = await vs.search(
            query_vec,
            tenant_id=tenant_id,
            top_k=top_k,
            category_filter=["image"],  # 复用 category 字段区分图片
            document_id_filter=document_id_filter,
            audience_filter=None,  # 图片不受 audience 限制
        )
    except Exception as e:
        logger.warning("pgvector image search failed: %s", e)
        return []
    if not raw_hits:
        return []

    # 3. 批量查 image_chunks 拿元信息 (page / width / height)
    document_ids = list({h.get("document_id") for h in raw_hits if h.get("document_id")})
    async with async_session_maker() as session:
        stmt = select(ImageChunk).where(
            ImageChunk.tenant_id == tenant_id,
        )
        if document_ids:
            stmt = stmt.where(ImageChunk.document_id.in_(document_ids))
        rows = (await session.execute(stmt)).scalars().all()

    by_doc: dict = {}
    for r in rows:
        by_doc.setdefault(r.document_id, r)

    # 4. 拼结果 (按向量 hit 顺序, 取每条对应的 image_chunks)
    results = []
    for h in raw_hits:
        doc_id = h.get("document_id", "")
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
            "score": h.get("score", 0.0),
        })
    return results
