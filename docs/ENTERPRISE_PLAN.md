# Enterprise Plan v2.0

> Integration: PROJECT_OPTIMIZATION_PLAN.md v1 + 4 long-term memory docs + MinerU deployment learning
> Goal: Each module - specific tasks - enterprise-grade - executable
> Status: 8 modules / 60+ tasks / Completed 35% / In-progress 10%

---

## Key Decisions (Based on Learning Notes + Practice)

| Dimension | v1 plan | v2 plan (this) | Reference |
|-----------|---------|----------------|-----------|
| PDF parsing | Docling/LlamaParse | MinerU (pipeline CPU default) | ekbs + Joyoung |
| Business DB | SQLite | PostgreSQL (parent + business) | User decision |
| Vector DB | Qdrant | Milvus (child + parent_id) | ekbs |
| WSL storage | C drive | E drive (10.75GB migrated) | User |
| Data model | dict in metadata | ParentChunk+ChildChunk standard | ekbs |
| Agent | keyword intent | LLM intent + ReAct + keyword fallback | Joyoung |
| Deployment | Docker Desktop | WSL Docker + MinerU remote | No GPU |
## Current State (2026-08-04)

- Tests: 36/36 passing
- Code: 53 Python files
- MinerU: 3.4.4 installed, models 2.5GB on E drive
- WSL: 21GB migrated to E drive
- C drive: from 0.25GB to 17.29GB freed

**Done**: 4 doc parsers, SSRF, MinerU 3-backend, 36 tests, 5-layer agent, KB mgmt API+UI
**In-progress**: MinerU parse 31MB PDF, WSL Docker deploy, storage refactor (parent to PG / child to Milvus)

---

# Module L0: Data Layer

## L0-P0-01: PostgreSQL deploy + data migration
- Status: TODO
- Tasks:
  - [ ] L0-P0-01a: WSL Docker pull postgres:16-alpine
  - [ ] L0-P0-01b: docker-compose.yml add postgres service
  - [ ] L0-P0-01c: Refactor app/db/session.py to support PG
  - [ ] L0-P0-01d: SQLAlchemy 2.0 PG-compatible
  - [ ] L0-P0-01e: Migration script alembic upgrade head
- Reference: ekbs MongoDB
- Workload: 2 days

## L0-P0-02: ParentChunk table + Document table
- Status: TODO
- Tasks:
  - [ ] L0-P0-02a: app/db/models.py add Document
  - [ ] L0-P0-02b: Add ParentChunk (parent_id PK, content TEXT)
  - [ ] L0-P0-02c: Add ChunkRelation
  - [ ] L0-P0-02d: Add composite index
- Reference: ekbs ChildChunk/ParentChunk
- Workload: 1 day

## L0-P0-03: Alembic auto-migration
- Status: TODO
- Tasks:
  - [ ] L0-P0-03a: app/main.py lifespan add migration
  - [ ] L0-P0-03b: Failure rollback
  - [ ] L0-P0-03c: /health return migration version
- Workload: 0.5 day

## L0-P1-01: Knowledge update (incremental + TTL)
- Tasks:
  - [ ] L0-P1-01a: Upsert by document_id
  - [ ] L0-P1-01b: Version + stale detection
  - [ ] L0-P1-01c: Soft delete
  - [ ] L0-P1-01d: 7-day archive
- Workload: 1.5 days

## L0-P1-02: Redis cache (ekbs)
- Tasks:
  - [ ] L0-P1-02a: docker-compose add redis:7-alpine
  - [ ] L0-P1-02b: Hot doc cache
  - [ ] L0-P1-02c: Retrieval result cache
- Workload: 1 day
---

# Module L1: RAG Engine

## L1-P0-01: MinerU real deployment
- Status: In-progress
- Tasks:
  - [x] L1-P0-01a: pip install mineru[all]
  - [x] L1-P0-01b: Models to E drive (2.5GB)
  - [ ] L1-P0-01c: Parse user PDF (31MB)
  - [ ] L1-P0-01d: Add MinerU result to RAG pipeline
  - [ ] L1-P0-01e: Health check + timeout retry
- Reference: MinerU 3.4 docs
- Workload: 1 day

## L1-P0-02: Word numbering full parsing (ekbs)
- Status: TODO
- Tasks:
  - [ ] L1-P0-02a: Parse numbering.xml
  - [ ] L1-P0-02b: Detect Heading 1/2/3
  - [ ] L1-P0-02c: Numbered list
  - [ ] L1-P0-02d: Test set
- Reference: ekbs Word
- Workload: 2 days

## L1-P0-03: Excel merged cells expand (ekbs)
- Status: TODO
- Tasks:
  - [ ] L1-P0-03a: Load workbook + colspan/rowspan
  - [ ] L1-P0-03b: 256 rows/chunk
  - [ ] L1-P0-03c: HTML render
  - [ ] L1-P0-03d: Test Joyoung 533 merged cells
- Reference: ekbs Excel
- Workload: 1.5 days

## L1-P0-04: Storage refactor (child to Milvus / parent to PG)
- Status: In-progress
- Tasks:
  - [ ] L1-P0-04a: Milvus deploy
  - [ ] L1-P0-04b: docker-compose add milvus
  - [ ] L1-P0-04c: engine.py split write
  - [ ] L1-P0-04d: Retrieval batch query PG
  - [ ] L1-P0-04e: Data migration
- Reference: ekbs data model
- Workload: 3 days

## L1-P1-01: Hybrid search (vector + BM25)
- Status: TODO
- Tasks:
  - [ ] L1-P1-01a: jieba + BM25
  - [ ] L1-P1-01b: Dual recall
  - [ ] L1-P1-01c: RRF fusion
  - [ ] L1-P1-01d: Eval compare
- Workload: 1.5 days

## L1-P1-02: Query rewrite (6 strategies)
- Status: TODO
- Tasks:
  - [ ] L1-P1-02a: Normalization
  - [ ] L1-P1-02b: Multi-Query
  - [ ] L1-P1-02c: Decomposition
  - [ ] L1-P1-02d: Step-back
  - [ ] L1-P1-02e: HyDE
  - [ ] L1-P1-02f: Self-Query
- Workload: 1 day

## L1-P1-03: Context compression
- Status: TODO
- Tasks:
  - [ ] L1-P1-03a: Selective extraction
  - [ ] L1-P1-03b: Query summary
  - [ ] L1-P1-03c: Structured extraction
- Workload: 1 day

## L1-P1-04: VLM image parsing (ekbs)
- Status: TODO
- Tasks:
  - [ ] L1-P1-04a: Extract images
  - [ ] L1-P1-04b: Multi-modal LLM
  - [ ] L1-P1-04c: Description as chunk
  - [ ] L1-P1-04d: Long image chunk
- Reference: ekbs Image
- Workload: 2 days

## L1-P1-05: Markdown placeholder (ekbs)
- Status: TODO
- Tasks:
  - [ ] L1-P1-05a: TABLE_PLACEHOLDER
  - [ ] L1-P1-05b: IMAGE_PLACEHOLDER
  - [ ] L1-P1-05c: Re-insert
- Workload: 1 day

## L1-P1-06: OCR fallback
- Status: TODO
- Tasks:
  - [ ] L1-P1-06a: Trigger OCR
  - [ ] L1-P1-06b: Landscape rotate
  - [ ] L1-P1-06c: chi_sim+eng
- Reference: Joyoung landscape
- Workload: 0.5 day

## L1-P2-01: Evaluation set (50 queries)
- Status: TODO
- Tasks:
  - [ ] L1-P2-01a: Write 50 queries
  - [ ] L1-P2-01b: 4 metrics
  - [ ] L1-P2-01c: Auto-eval script
- Workload: 1.5 days
---

# Module L2: Agent

## L2-P0-01: 5-layer architecture
- Status: 80% done
- Tasks:
  - [x] L2-P0-01a: 5 layers implemented
  - [ ] L2-P0-01b: Middleware onion chain test
  - [ ] L2-P0-01c: Immutable messages
  - [ ] L2-P0-01d: Persist to PG
- Reference: AgentScope 5-layer
- Workload: 1 day

## L2-P0-02: Long-term memory
- Status: TODO
- Tasks:
  - [ ] L2-P0-02a: LLM extract facts
  - [ ] L2-P0-02b: Write user_profiles
  - [ ] L2-P0-02c: Auto-load system prompt
  - [ ] L2-P0-02d: user_id isolation
- Workload: 1.5 days

## L2-P1-01: Skill library (Progressive Disclosure)
- Status: TODO
- Tasks:
  - [ ] L2-P1-01a: Skill middleware
  - [ ] L2-P1-01b: Skill vector index
  - [ ] L2-P1-01c: 20+ business skills
- Workload: 2 days

## L2-P1-02: HITL for confirm_order
- Status: TODO
- Tasks:
  - [ ] L2-P1-02a: ASKING state trigger
  - [ ] L2-P1-02b: Frontend modal
  - [ ] L2-P1-02c: resolve_ask resume
  - [ ] L2-P1-02d: Reject rollback
- Workload: 1.5 days

## L2-P1-03: Loop Engineering
- Status: TODO
- Tasks:
  - [ ] L2-P1-03a: trace_id
  - [ ] L2-P1-03b: Context utilization monitor
  - [ ] L2-P1-03c: Replay script
  - [ ] L2-P1-03d: A/B test
- Workload: 1.5 days

## L2-P1-04: Subagent orchestration
- Status: TODO
- Tasks:
  - [ ] L2-P1-04a: knowledge agent
  - [ ] L2-P1-04b: booking agent
  - [ ] L2-P1-04c: Main agent routing
  - [ ] L2-P1-04d: Inter-agent message
- Workload: 2 days

## L2-P2-01: MCP integration
- Status: TODO
- Tasks:
  - [ ] L2-P2-01a: MCP Server SDK
  - [ ] L2-P2-01b: 5 core tools
  - [ ] L2-P2-01c: Claude Desktop compatible
- Workload: 1 day
---

# Module L3: LLM

## L3-P0-01: Streaming LLM
- Status: TODO
- Tasks:
  - [ ] L3-P0-01a: text/event-stream
  - [ ] L3-P0-01b: stream=True
  - [ ] L3-P0-01c: Frontend EventSource
- Workload: 1.5 days

## L3-P1-01: LLM Gateway
- Status: TODO
- Tasks:
  - [ ] L3-P1-01a: Vendor adapters
  - [ ] L3-P1-01b: Route strategy
  - [ ] L3-P1-01c: Fallback chain
  - [ ] L3-P1-01d: Rate limit
- Reference: ekbs LLMBundle
- Workload: 2 days

## L3-P1-02: Structured output (FC)
- Status: TODO
- Tasks:
  - [ ] L3-P1-02a: Tool schema
  - [ ] L3-P1-02b: Parse result
  - [ ] L3-P1-02c: json_repair
- Workload: 1 day

## L3-P1-03: Multi-modal LLM
- Status: TODO
- Tasks:
  - [ ] L3-P1-03a: 5 LLM types
  - [ ] L3-P1-03b: Factory
  - [ ] L3-P1-03c: Multi-vendor
- Reference: ekbs LLMBundle
- Workload: 1.5 days

---

# Module L4: Frontend

## L4-P0-01: SSE integration
- Status: TODO
- Tasks:
  - [ ] L4-P0-01a: EventSource wrapper
  - [ ] L4-P0-01b: Streaming render
  - [ ] L4-P0-01c: AbortController
- Workload: 1 day

## L4-P1-01: H5 mobile
- Status: TODO
- Tasks:
  - [ ] L4-P1-01a: CSS media query
  - [ ] L4-P1-01b: Touch event
  - [ ] L4-P1-01c: WeChat test
- Workload: 0.5 day

## L4-P1-02: KB admin UI
- Status: TODO
- Tasks:
  - [ ] L4-P1-02a: Drag upload
  - [ ] L4-P1-02b: Real-time status SSE
  - [ ] L4-P1-02c: Recall tester
  - [ ] L4-P1-02d: Operation history
- Workload: 2 days

## L4-P1-03: HITL modal
- Status: TODO
- Tasks:
  - [ ] L4-P1-03a: Order confirm modal
  - [ ] L4-P1-03b: Countdown 30s
  - [ ] L4-P1-03c: Voice/text
- Workload: 0.5 day
---

# Module L5: DevOps

## L5-P0-01: Prometheus metrics
- Status: TODO
- Tasks:
  - [ ] L5-P0-01a: Counter
  - [ ] L5-P0-01b: Histogram
  - [ ] L5-P0-01c: Gauge
  - [ ] L5-P0-01d: docker-compose Prometheus+Grafana
  - [ ] L5-P0-01e: Business dashboard
- Workload: 1.5 days

## L5-P0-02: Structured logging
- Status: TODO
- Tasks:
  - [ ] L5-P0-02a: JSON Formatter
  - [ ] L5-P0-02b: contextvars inject trace_id
  - [ ] L5-P0-02c: docker-compose Loki+Promtail
  - [ ] L5-P0-02d: Grafana log
- Workload: 1 day

## L5-P1-01: HTTPS + Nginx
- Status: TODO
- Tasks:
  - [ ] L5-P1-01a: Cert
  - [ ] L5-P1-01b: nginx.conf
  - [ ] L5-P1-01c: HSTS/CORS
- Workload: 1 day

## L5-P1-02: CI/CD
- Status: TODO
- Tasks:
  - [ ] L5-P1-02a: GitHub Actions
  - [ ] L5-P1-02b: Docker buildx
  - [ ] L5-P1-02c: Auto deploy test
  - [ ] L5-P1-02d: Manual prod
- Workload: 1 day

## L5-P1-03: Milvus + PG + Redis real deploy
- Status: In-progress
- Tasks:
  - [ ] L5-P1-03a: WSL Docker mirror
  - [ ] L5-P1-03b: docker-compose full
  - [ ] L5-P1-03c: E drive volumes
  - [ ] L5-P1-03d: Health check
- Workload: 1.5 days

## L5-P2-01: Backup + DR
- Status: TODO
- Tasks:
  - [ ] L5-P2-01a: PG backup
  - [ ] L5-P2-01b: Milvus snapshot
  - [ ] L5-P2-01c: Recovery drill
- Workload: 1 day

---

# Module L6: Business

## L6-P0-01: JWT startup check
- Status: DONE

## L6-P1-01: Draft order expiration
- Status: TODO
- Tasks:
  - [ ] L6-P1-01a: APScheduler daily
  - [ ] L6-P1-01b: Soft delete + notify
- Workload: 0.5 day

## L6-P1-02: Business hours check
- Status: TODO
- Tasks:
  - [ ] L6-P1-02a: Configurable
  - [ ] L6-P1-02b: Frontend hint
  - [ ] L6-P1-02c: API check
- Workload: 0.5 day

## L6-P1-03: SMS verification
- Status: TODO
- Tasks:
  - [ ] L6-P1-03a: Aliyun SMS
  - [ ] L6-P1-03b: Send + verify
  - [ ] L6-P1-03c: Anti-spam
  - [ ] L6-P1-03d: Code table
- Workload: 1 day

## L6-P2-01: Review system
- Status: TODO
- Tasks:
  - [ ] L6-P2-01a: Review table
  - [ ] L6-P2-01b: To vector DB
  - [ ] L6-P2-01c: Stylist rating
- Workload: 2 days

## L6-P2-02: Recommendation
- Status: TODO
- Tasks:
  - [ ] L6-P2-02a: Collaborative filter
  - [ ] L6-P2-02b: Tag match
  - [ ] L6-P2-02c: Composite sort
- Workload: 2 days
---

# Module L7: Security

## L7-P0-01: SSRF protection
- Status: DONE (need more tests)
- Tasks:
  - [ ] L7-P0-01a: 10+ attack payload unit test
  - [ ] L7-P0-01b: Document blocklist

## L7-P0-02: Rate-limit download (ekbs)
- Status: TODO
- Tasks:
  - [ ] L7-P0-02a: 4KB stream chunk
  - [ ] L7-P0-02b: max_size check
  - [ ] L7-P0-02c: 1GB test
- Reference: ekbs download_file
- Workload: 0.5 day

## L7-P0-03: Input validation
- Status: TODO
- Tasks:
  - [ ] L7-P0-03a: Pydantic strict
  - [ ] L7-P0-03b: MIME check
  - [ ] L7-P0-03c: Size limit
  - [ ] L7-P0-03d: SQL injection
- Workload: 1 day

## L7-P1-01: Sensitive word filter
- Status: TODO
- Tasks:
  - [ ] L7-P1-01a: Word library
  - [ ] L7-P1-01b: Dual filter
  - [ ] L7-P1-01c: Alert + intercept
- Workload: 1 day

## L7-P1-02: Audit log
- Status: TODO
- Tasks:
  - [ ] L7-P1-02a: Key operations
  - [ ] L7-P1-02b: Append-only
  - [ ] L7-P1-02c: 90-day retention
- Workload: 1 day

---

# Module L8: Quality

## L8-P0-01: Unit test coverage
- Status: 36 tests now
- Tasks:
  - [ ] L8-P0-01a: pytest-cov
  - [ ] L8-P0-01b: Core 100% cover
  - [ ] L8-P0-01c: CI coverage gate
- Workload: 2 days

## L8-P0-02: Integration test
- Status: TODO
- Tasks:
  - [ ] L8-P0-02a: E2E flow
  - [ ] L8-P0-02b: Multi-tenant
  - [ ] L8-P0-02c: Permission reject
  - [ ] L8-P0-02d: Eval per PR
- Workload: 2 days

## L8-P1-01: Performance test
- Status: TODO
- Tasks:
  - [ ] L8-P1-01a: Locust 100 concurrent
  - [ ] L8-P1-01b: P99 < 500ms
  - [ ] L8-P1-01c: 30MB PDF < 60s
- Workload: 1.5 days

## L8-P1-02: Documentation
- Status: TODO
- Tasks:
  - [ ] L8-P1-02a: OpenAPI
  - [ ] L8-P1-02b: PlantUML
  - [ ] L8-P1-02c: Deploy manual
  - [ ] L8-P1-02d: Ops manual
- Workload: 2 days
---

# Execution Roadmap

## Stage 1: Foundation (1 week - current)
- L0-P0-01 to 03: PG + ParentChunk + Alembic
- L1-P0-01: MinerU parse 1225 page PDF
- L1-P0-04: Storage refactor
- L5-P1-03: Full Docker deploy

## Stage 2: Core capability (2 weeks)
- L1-P0-02/03: Word/Excel full parse
- L1-P1-01/02/04: Hybrid/Rewrite/VLM
- L2-P0-02: Long-term memory
- L2-P1-02: HITL
- L3-P0-01/L4-P0-01: SSE streaming
- L5-P0-01/02: Monitor + log

## Stage 3: Enterprise polish (2-3 weeks)
- L1-P1-03/05: Compression/placeholder
- L1-P2-01: Eval set
- L2-P1-01/03/04: Skills/Loop/Subagent
- L2-P2-01: MCP
- L3-P1-01/02/03: Gateway/FC/Multi-modal
- L5-P1-01/02: HTTPS/CI/CD
- L6-P1-01 to 03: Draft/hours/SMS
- L7-P0-02/03: Rate limit/validation
- L8: Test + doc

## Stage 4: Advanced (ongoing)
- L1-P1-04: VLM image
- L2-P2-01: MCP
- L3-P1-03: Multi-modal LLM
- L5-P2-01: Backup recovery
- L6-P2-01/02: Review/recommend

---

# Total Workload Estimate

| Stage | Workload | Cumulative |
|-------|----------|------------|
| Stage 1 | 6 days | 6 days |
| Stage 2 | 14 days | 20 days |
| Stage 3 | 16 days | 36 days |
| Stage 4 | 5+ days | 41+ days |

---

# Top 5 Immediate (Today/Tomorrow)

1. **L1-P0-01c**: Run MinerU parse 31MB PDF (validate pipeline end-to-end)
2. **L0-P0-01a to c**: WSL Docker pull postgres + add docker-compose service
3. **L0-P0-02a to c**: Add Document/ParentChunk models
4. **L1-P0-04a/b**: WSL Docker pull milvus image + compose
5. **L1-P0-04c**: engine.py split write (parent to PG / child to Milvus)

---

# References

| Source | File | Reference |
|--------|------|-----------|
| AgentScope 5-layer | [LONG_TERM_MEMORY_AI_AGENT.md](LONG_TERM_MEMORY_AI_AGENT.md) | 5-layer/ReAct/middleware/HITL/memory |
| ekbs doc parsing | [LONG_TERM_MEMORY_EKBS_AI_SERVICE.md](LONG_TERM_MEMORY_EKBS_AI_SERVICE.md) | 6 parsers/data model/SSRF/LLMBundle/Redis |
| Joyoung POC | [LONG_TERM_MEMORY_JOYOUNG_POC.md](LONG_TERM_MEMORY_JOYOUNG_POC.md) | 12 business scenarios/landscape OCR/7 sub-agents |
| JavaGuide AI | [LONG_TERM_MEMORY_JAVAGUIDE_AI.md](LONG_TERM_MEMORY_JAVAGUIDE_AI.md) | Java reference ideas |
| MinerU official | https://github.com/opendatalab/MinerU | 3 backends/86% 95% accuracy |
| Original plan v1 | [PROJECT_OPTIMIZATION_PLAN.md](PROJECT_OPTIMIZATION_PLAN.md) | 6 modules/50 tasks/decisions |
