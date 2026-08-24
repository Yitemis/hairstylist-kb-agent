# RAG v2 eval: Plugin Pipeline comparison
import asyncio, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

async def main():
    from app.rag.chat_pipeline import PipelineContext, get_default_runner
    from app.rag.evaluation.eval_set_en import EVAL_SET_EN
    from app.rag.evaluation.eval_set import EVAL_SET
    from app.rag.evaluation.metrics import aggregate_metrics, hit_rate, mrr, ndcg_at_k, recall_at_k
    from app.rag.evaluation.ragas_runner import evaluate_rag, RAGASResult
    from app.rag.v2_engine import reset_state
    reset_state()
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    eval_set = EVAL_SET_EN if lang == "en" else EVAL_SET
    print("Running Plugin Pipeline eval (" + str(len(eval_set)) + " queries, lang=" + lang + ")")
    runner = get_default_runner()
    per_query = []
    ragas_results = []
    gate_dist = {}
    total_phase_ms = {}
    for i, eq in enumerate(eval_set, 1):
        ctx = PipelineContext(user_id=0, message=eq.query, session_id="eval_" + str(i), tenant_id="demo", audience_filter=["user", "all"])
        t0 = time.time()
        ctx = await runner.run(ctx)
        total_ms = int((time.time() - t0) * 1000)
        gate_dist[ctx.gate_decision] = gate_dist.get(ctx.gate_decision, 0) + 1
        for p, ms in ctx.phase_latencies.items():
            total_phase_ms[p] = total_phase_ms.get(p, 0) + ms
        docs = [c.get("content", "") for c in ctx.context_chunks]
        r5 = recall_at_k(docs, eq.expected_keywords, 5)
        r10 = recall_at_k(docs, eq.expected_keywords, 10)
        m = mrr(docs, eq.expected_keywords)
        h5 = hit_rate(docs, eq.expected_keywords, 5)
        n5 = ndcg_at_k(docs, eq.expected_keywords, 5)
        per_query.append({"query": eq.query, "category": eq.category, "expected_keywords": eq.expected_keywords, "retrieved_count": len(docs), "top_docs": docs[:3], "recall_at_5": r5, "recall_at_10": r10, "mrr": m, "hit_rate_at_5": h5, "ndcg_at_5": n5, "gate_decision": ctx.gate_decision, "top1_score": ctx.top1_score, "latency_ms": total_ms, "answer": ctx.answer})
        if ctx.answer and not ctx.answer.startswith("Sorry") and len(ctx.answer) > 5 and ctx.gate_decision != "refuse":
            ragas = evaluate_rag(query=eq.query, answer=ctx.answer, retrieved_contexts=docs, expected_keywords=eq.expected_keywords, use_ragas=False)
            ragas_results.append(ragas)
        if i % 5 == 0:
            print("  [" + str(i) + "/" + str(len(eval_set)) + "] gate=" + ctx.gate_decision + " top1=" + str(round(ctx.top1_score, 3)) + " r5=" + str(round(r5, 2)) + " " + str(total_ms) + "ms")
    summary = aggregate_metrics([{k: v for k, v in r.items() if k not in ("query", "category", "expected_keywords", "top_docs", "gate_decision", "answer")} for r in per_query])
    ragas_avg = None
    if ragas_results:
        n = len(ragas_results)
        ragas_avg = RAGASResult(faithfulness=sum(r.faithfulness for r in ragas_results) / n, answer_relevancy=sum(r.answer_relevancy for r in ragas_results) / n, context_precision=sum(r.context_precision for r in ragas_results) / n, context_recall=sum(r.context_recall for r in ragas_results) / n, details={"count": n})
    print("")
    print("=" * 60)
    print("RAG Pipeline Evaluation Report (Plugin Pipeline)")
    print("=" * 60)
    print("[Overall] count=" + str(summary["count"]))
    for k, v in summary.items():
        if k != "count":
            print("  " + k + ": " + str(round(v, 3)))
    print("[Gate Distribution]")
    for k, v in gate_dist.items():
        print("  " + k + ": " + str(v))
    print("[Phase Latency (total ms)]")
    total_ms_all = sum(total_phase_ms.values()) or 1
    for p, ms in sorted(total_phase_ms.items(), key=lambda x: -x[1]):
        print("  " + p + ": " + str(ms) + "ms (" + str(round(ms/total_ms_all*100)) + "%)")
    if ragas_avg:
        print("[RAGAS 4-dim (heuristic, n=" + str(ragas_avg.details["count"]) + ")]")
        print("  faithfulness:    " + str(round(ragas_avg.faithfulness, 3)))
        print("  answer_relevancy:" + str(round(ragas_avg.answer_relevancy, 3)))
        print("  context_precision:" + str(round(ragas_avg.context_precision, 3)))
        print("  context_recall:   " + str(round(ragas_avg.context_recall, 3)))
    print("[By Category]")
    by_cat = {}
    for r in per_query:
        by_cat.setdefault(r["category"], []).append(r)
    for cat, rs in by_cat.items():
        avg_mrr = sum(x["mrr"] for x in rs) / len(rs)
        avg_r5 = sum(x["recall_at_5"] for x in rs) / len(rs)
        avg_n5 = sum(x["ndcg_at_5"] for x in rs) / len(rs)
        print("  " + cat + ": n=" + str(len(rs)) + " recall@5=" + str(round(avg_r5, 3)) + " mrr=" + str(round(avg_mrr, 3)) + " ndcg@5=" + str(round(avg_n5, 3)))
    print("[Failed Queries (recall@5 < 0.3)]")
    failed = [r for r in per_query if r["recall_at_5"] < 0.3]
    for r in failed[:5]:
        print("  [" + r["category"] + "] " + r["query"][:50] + "... -> r5=" + str(round(r["recall_at_5"], 2)) + " gate=" + r["gate_decision"] + " top1=" + str(round(r["top1_score"], 3)))
    return {"summary": summary, "ragas": ragas_avg, "gate_dist": gate_dist, "phase_ms": total_phase_ms, "per_query": per_query}

if __name__ == "__main__":
    asyncio.run(main())
