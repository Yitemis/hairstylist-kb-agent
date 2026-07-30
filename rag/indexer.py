# -*- coding: utf-8 -*-
"""索引器：文档 → 父子分块 → 子块向量化 → 写入 Milvus。

串起三层能力：

1. :func:`rag.pipeline.build_records` —— 解析 + 父子分块 + 元数据；
2. 火山方舟 embedding —— 子块文本向量化；
3. :class:`rag.store.VectorStore` —— 显式 Schema 写入 Milvus。

对外暴露 :func:`index_file`（索引单文件）与 :func:`index_directory`
（批量索引目录），供命令行脚本与服务层调用。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from rag.pipeline import IndexRecord, build_records
from rag.store import VectorStore

logger = logging.getLogger(__name__)


def _make_store() -> VectorStore:
    """按配置构建向量库连接。"""
    from app.core.config import vector_store_config as cfg

    uri = cfg.uri or f"http://{cfg.host}:{cfg.port}"
    return VectorStore(
        uri=uri,
        collection=cfg.collection,
        dim=cfg.dims,
        metric_type=cfg.metric_type,
    )


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """调用火山方舟 embedding 批量向量化子块文本。"""
    from agentscope.message import TextBlock

    from app.embedding import build_embedding_model

    model = build_embedding_model()
    resp = await model([TextBlock(text=t) for t in texts])
    return resp.embeddings


def _record_to_row(record: IndexRecord, vector: list[float]) -> dict[str, Any]:
    """把 IndexRecord + 向量组装成 Milvus 行（标量字段扁平化）。"""
    return {
        "record_id": record.record_id,
        "vector": vector,
        "text": record.text[:8000],
        "parent_id": record.parent_id,
        "parent_text": record.parent_text[:16000],
        "tenant_id": record.tenant_id,
        "permission": record.permission,
        "doc_id": record.doc_id,
        "filename": record.filename,
        "category": record.category,
        "section_path": " / ".join(record.section)[:500],
        "kind": record.kind,
        "models": ",".join(record.models)[:500],
    }


async def index_file(
    file_uri: str,
    *,
    doc_id: str,
    tenant_id: str = "default",
    permission: str = "public",
    category: str = "general",
    store: VectorStore | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    """索引单个文件：分块 → 向量化 → 写入 Milvus。

    Args:
        file_uri: 文件路径或安全 URL。
        doc_id: 文档唯一 ID。
        tenant_id: 租户 ID。
        permission: 权限标签。
        category: 业务分类。
        store: 复用的向量库连接，缺省新建。
        replace: 为真时先删除该文档旧子块再写入（幂等重建）。

    Returns:
        含子块数、耗时等信息的结果字典。
    """
    import time

    start = time.time()
    store = store or _make_store()

    records = build_records(
        file_uri, doc_id=doc_id, tenant_id=tenant_id,
        permission=permission, category=category,
    )
    if not records:
        return {"status": "empty", "doc_id": doc_id, "chunks": 0}

    vectors = await _embed_texts([r.text for r in records])
    rows = [_record_to_row(r, v) for r, v in zip(records, vectors)]

    if replace:
        store.delete_by_doc(tenant_id, doc_id)
    written = store.upsert(rows)

    elapsed = int((time.time() - start) * 1000)
    logger.info("索引完成 %s: %d 子块, %dms", doc_id, written, elapsed)
    return {
        "status": "ok",
        "doc_id": doc_id,
        "tenant_id": tenant_id,
        "chunks": written,
        "parents": len({r.parent_id for r in records}),
        "time_ms": elapsed,
    }


def _guess_category(filename: str) -> str:
    """按文件名关键词推断业务分类。"""
    if any(k in filename for k in ("染烫", "烫发", "染发")):
        return "染烫技术"
    if any(k in filename for k in ("洗护", "洗发", "护理")):
        return "洗护产品"
    if any(k in filename for k in ("话术", "服务", "流程")):
        return "服务话术"
    return "general"


async def index_directory(
    directory: str | Path = "data/knowledge",
    *,
    tenant_id: str = "default",
    permission: str = "public",
    patterns: tuple[str, ...] = ("*.md", "*.txt", "*.pdf", "*.docx", "*.xlsx"),
    max_concurrent_files: int = 4,
) -> dict[str, Any]:
    """批量索引目录下受支持的文档（并发处理）。

    Args:
        directory: 待索引目录。
        tenant_id: 租户 ID。
        permission: 权限标签。
        patterns: 需要索引的文件扩展名。
        max_concurrent_files: 最大并发处理的文件数（避免 API 限流）。
    """
    directory = Path(directory)
    files: list[Path] = []
    for pat in patterns:
        files.extend(sorted(directory.glob(pat)))

    if not files:
        return {"status": "empty", "files": 0, "chunks": 0}

    store = _make_store()
    sem = asyncio.Semaphore(max_concurrent_files)

    async def _index_one(path: Path) -> dict[str, Any]:
        async with sem:
            result = await index_file(
                str(path.resolve()),
                doc_id=path.stem,
                tenant_id=tenant_id,
                permission=permission,
                category=_guess_category(path.name),
                store=store,
            )
            return {"file": path.name, **result}

    tasks = [_index_one(path) for path in files]
    details = await asyncio.gather(*tasks)
    total_chunks = sum(d.get("chunks", 0) for d in details)

    return {
        "status": "ok",
        "files": len(files),
        "chunks": total_chunks,
        "total_in_store": store.count(tenant_id),
        "details": details,
    }


def _cli() -> None:
    """命令行入口：``python -m rag.indexer [--clean]``。"""
    import argparse

    parser = argparse.ArgumentParser(description="知识库索引工具（父子分块 + 向量入库）")
    parser.add_argument("--dir", default="data/knowledge", help="待索引目录")
    parser.add_argument("--tenant", default="default", help="租户 ID")
    parser.add_argument("--clean", action="store_true", help="先清空集合再索引")
    args = parser.parse_args()

    if args.clean:
        _make_store().clear()
        print("已清空集合")

    result = asyncio.run(index_directory(args.dir, tenant_id=args.tenant))
    print(f"\n索引完成: {result['files']} 个文件, {result['chunks']} 个子块")
    print(f"集合内总子块数: {result.get('total_in_store')}")
    for d in result.get("details", []):
        print(f"  - {d['file']}: {d.get('chunks', 0)} 子块 / {d.get('parents', 0)} 父块")


if __name__ == "__main__":
    _cli()
