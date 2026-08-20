# -*- coding: utf-8 -*-
"""Milvus → pgvector 一次性数据迁移 (P2-基础设施).

策略: 不直连 Milvus 抽数据 (schema 不同), 而是:
1. 从 PG 读所有 Document (status=indexed, not deleted)
2. 重新读磁盘上的原文件 → 重新走 index_document() 入 pgvector
3. pgvector 走 ensure_collection (空操作) + 实际批量 insert
4. Milvus 数据保留 N 天做回滚缓冲 (如果需要)

用法:
    python scripts/migrate_milvus_to_pgvector.py [--dry-run] [--tenant=default]

注意:
- 迁移前请确保 alembic upgrade head 已执行 (0011_pgvector_setup.py)
- 迁移过程中 Document.is_published 保持不变 (旧索引自动按 PG 状态过滤)
- index_document 内部会跳过已存在的 parent_id, 多次跑幂等
"""
import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本能找到 app 包
sys.path.insert(0, str(Path(__file__).parent.parent))


async def migrate(tenant_id: str = None, dry_run: bool = False) -> dict:
    """执行迁移."""
    from sqlalchemy import select, update
    from app.db.session import async_session_maker
    from app.db.models import Document
    from app.rag.v2_engine import (
        index_document, reset_state, get_vector_store,
    )

    reset_state()
    vs = await get_vector_store()
    print(f"[MIGRATE] 向量库: {type(vs).__name__}")

    async with async_session_maker() as s:
        stmt = select(Document).where(
            Document.mineru_status == "indexed",
            Document.deleted_at.is_(None),
        )
        if tenant_id:
            stmt = stmt.where(Document.tenant_id == tenant_id)
        docs = (await s.execute(stmt.order_by(Document.created_at))).scalars().all()

    print(f"[MIGRATE] 找到 {len(docs)} 个已索引文档")

    if dry_run:
        print("[MIGRATE] DRY RUN 模式, 不写入")
        for d in docs:
            print(f"  - {d.document_id} | {d.filename} | tenant={d.tenant_id}")
        return {"total": len(docs), "migrated": 0, "skipped": 0, "failed": 0}

    # 先清空 child_chunks (避免重复 + 旧数据残留)
    from sqlalchemy import text
    async with async_session_maker() as s:
        if tenant_id:
            await s.execute(
                text("DELETE FROM child_chunks WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        else:
            await s.execute(text("TRUNCATE TABLE child_chunks"))
        await s.commit()
    print("[MIGRATE] 已清空 child_chunks 表")

    upload_dir = Path("data/uploads")
    if not upload_dir.exists():
        print(f"[ERROR] 上传目录不存在: {upload_dir}")
        return {"total": 0, "migrated": 0, "skipped": 0, "failed": 0}

    stats = {"total": len(docs), "migrated": 0, "skipped": 0, "failed": 0}
    for i, doc in enumerate(docs, 1):
        # 找磁盘文件
        file_path = None
        for p in upload_dir.iterdir():
            if p.stem == doc.document_id:
                file_path = p
                break
        if not file_path:
            print(f"  [{i}/{len(docs)}] SKIP {doc.document_id} (file not found)")
            stats["skipped"] += 1
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            result = await index_document(
                document_id=doc.document_id,
                content=content,
                filename=doc.filename,
                tenant_id=doc.tenant_id,
                category=doc.category,
                audience=doc.audience or "all",
            )
            if result.get("status") == "ok":
                print(
                    f"  [{i}/{len(docs)}] OK {doc.document_id} -> "
                    f"{result['parents']} parents / {result['children']} children"
                )
                stats["migrated"] += 1
            else:
                print(f"  [{i}/{len(docs)}] SKIP {doc.document_id} ({result.get('status')})")
                stats["skipped"] += 1
        except Exception as e:
            print(f"  [{i}/{len(docs)}] FAIL {doc.document_id}: {e}")
            stats["failed"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Milvus → pgvector 数据迁移")
    parser.add_argument("--dry-run", action="store_true", help="只看不动")
    parser.add_argument("--tenant", type=str, default=None, help="只迁移指定 tenant")
    args = parser.parse_args()

    print(f"[MIGRATE] 开始迁移 (tenant={args.tenant or 'ALL'}, dry_run={args.dry_run})")
    stats = asyncio.run(migrate(tenant_id=args.tenant, dry_run=args.dry_run))
    print()
    print("=" * 60)
    print(f"[MIGRATE] 完成: total={stats['total']} migrated={stats['migrated']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    print("=" * 60)
    print()
    print("后续步骤:")
    print("  1. 验证: psql -U hair -d hairstylist -c 'SELECT COUNT(*) FROM child_chunks'")
    print("  2. 跑 RAG 评估: python scripts/run_rag_evaluation.py")
    print("  3. 停 Milvus: wsl -d Ubuntu-Docker -- docker stop milvus-standalone milvus-etcd milvus-minio hairstylist-attu")
    print("  4. 删 milvus_store.py: rm app/rag/milvus_store.py")
    print("  5. 更新 requirements.txt: 删 pymilvus")


if __name__ == "__main__":
    main()
