"""把 MinerU 解析结果（md）灌入 RAG 引擎（v2_engine）。

用法：
    python scripts/ingest_mineru_output.py --md <path> --doc-id <id> --tenant <t>

MinerU 输出结构:
    <output>/<pdf_name>/auto/<pdf_name>.md
    <output>/<pdf_name>/auto/<pdf_name>_content_list.json  (结构化)
    <output>/<pdf_name>/auto/images/  (图片)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# 加项目根到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"), override=True)

# 配置 E 盘缓存
CACHE_BASE = Path("E:/cache")
os.environ.setdefault("TMPDIR", str(CACHE_BASE / "tmp"))
os.environ.setdefault("PIP_CACHE_DIR", str(CACHE_BASE / "pip"))
os.environ.setdefault("HF_HOME", str(CACHE_BASE / "huggingface"))
os.environ.setdefault("MODELSCOPE_CACHE", str(CACHE_BASE / "modelscope"))


async def main_async(md_path: str, doc_id: str, tenant_id: str, category: str = "general"):
    from app.rag.v2_engine import index_document

    md_path = Path(md_path)
    if not md_path.exists():
        print(f"MD file not found: {md_path}")
        return

    content = md_path.read_text(encoding="utf-8")
    print(f"Read MD: {len(content)} chars, {content.count(chr(10))} lines")

    result = await index_document(
        document_id=doc_id,
        content=content,
        filename=md_path.stem + ".pdf",
        tenant_id=tenant_id,
        category=category,
    )
    print(f"Indexed: {result}")


def main():
    parser = argparse.ArgumentParser(description="Ingest MinerU output into RAG")
    parser.add_argument("--md", required=True, help="Path to .md file from MinerU")
    parser.add_argument("--doc-id", required=True, help="Document ID (UUID)")
    parser.add_argument("--tenant", default="default", help="Tenant ID")
    parser.add_argument("--category", default="general", help="Category")
    args = parser.parse_args()

    asyncio.run(main_async(args.md, args.doc_id, args.tenant, args.category))


if __name__ == "__main__":
    main()
