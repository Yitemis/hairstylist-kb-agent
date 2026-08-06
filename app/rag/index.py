# -*- coding: utf-8 -*-
"""知识库批量索引工具。

用法：
    python -m app.rag.index           # 索引 data/knowledge 下所有 md 文件
    python -m app.rag.index --clean    # 先清空再索引
    python -m app.rag.index --stats    # 只统计不索引
"""
import argparse
import asyncio
from pathlib import Path

from app.rag.v2_engine import get_knowledge_stats, index_document


async def _index_file(path: Path, tenant_id: str) -> dict:
    """索引单个 Markdown 文件。"""
    content = path.read_text(encoding="utf-8")
    filename = path.name

    # 自动识别分类（根据文件名关键词）
    category = "general"
    if "染烫" in filename or "烫发" in filename or "染发" in filename:
        category = "染烫技术"
    elif "洗护" in filename or "洗发水" in filename or "护理" in filename:
        category = "洗护产品"
    elif "话术" in filename or "服务" in filename or "流程" in filename:
        category = "服务话术"

    return await index_document(
        document_id=f"doc_{path.stem}_{hash(content) % 10000}",
        content=content,
        filename=filename,
        tenant_id=tenant_id,
        category=category,
    )


async def index_all(knowledge_dir: Path = Path("data/knowledge"), tenant_id: str = "default") -> None:
    """批量索引目录下所有 Markdown 文件。"""
    if not knowledge_dir.exists():
        print(f"知识目录不存在: {knowledge_dir}")
        return

    md_files = list(knowledge_dir.glob("*.md"))
    if not md_files:
        print("未找到任何 Markdown 文件")
        return

    print(f"发现 {len(md_files)} 个文档，开始索引...")

    total_chunks = 0
    for idx, f in enumerate(md_files):
        result = await _index_file(f, tenant_id)
        if result.get("status") == "ok":
            chunks = result.get("chunks_indexed", 0)
            total_chunks += chunks
            print(f"  [{idx+1}/{len(md_files)}] {f.name} -> {chunks} 个子块")
        else:
            print(f"  [{idx+1}/{len(md_files)}] {f.name} -> 跳过")

    stats = await get_knowledge_stats(tenant_id)
    print(f"\n索引完成: {len(md_files)} 个文档, {total_chunks} 个子块")
    print(f"向量库总量: {stats['total_chunks']} 个子块 (tenant={tenant_id})")


async def show_stats(tenant_id: str = "default") -> None:
    """显示知识库统计信息。"""
    stats = await get_knowledge_stats(tenant_id)
    print(f"知识库统计 (tenant={tenant_id}):")
    print(f"  总向量数: {stats['total_chunks']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="美发知识库索引工具")
    parser.add_argument("--stats", action="store_true", help="只显示统计信息，不索引")
    parser.add_argument("--tenant", type=str, default="default", help="租户 ID，默认为 default")
    args = parser.parse_args()

    if args.stats:
        asyncio.run(show_stats(args.tenant))
    else:
        asyncio.run(index_all(tenant_id=args.tenant))


if __name__ == "__main__":
    main()