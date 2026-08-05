"""Run RAG evaluation against real data (30 page barber book).

用法:
    DATABASE_URL=... python scripts/run_rag_evaluation.py
"""
import asyncio
import sys
from pathlib import Path

# 加项目根
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)


async def main():
    from app.rag.evaluation.runner import run_evaluation, format_report
    from app.rag.v2_engine import retrieve, reset_state

    # reset_state only ONCE (not per query)
    reset_state()

    async def retrieve_fn(query, tenant_id, top_k):
        return await retrieve(
            query=query, tenant_id=tenant_id, top_k=top_k,
            enable_rerank=False,
        )

    print("Running RAG evaluation (30 queries)...")
    # 默认 EN (针对 30 页英文理发书)
    import sys
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    report = await run_evaluation(retrieve_fn, top_k=10, lang=lang)
    print(format_report(report))


if __name__ == "__main__":
    asyncio.run(main())
