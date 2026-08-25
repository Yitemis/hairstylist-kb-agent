---
skill_id: rag-knowledge-metadata
name: Add knowledge metadata fields for incremental update
description: Add 15 metadata fields to documents/parent_chunks/child_chunks (content_hash, version_id, is_deleted, embedding_model, etc.) for content-hash dedup + blue-green index switching
tags: [rag, metadata, migration, content-hash]
version: 1.0
estimated_time: 1 day
prerequisites:
  - Alembic setup
  - Knows current schema
---

# Add Knowledge Metadata

## Goal
Enable incremental update + content-hash dedup + index alias switching.

## New Fields (15 total)

**documents table** (9 fields):
- content_hash: VARCHAR(64), SHA-256, indexed
- version_id: INTEGER, default 1
- is_deleted: BOOLEAN, default false, indexed
- chunk_strategy: VARCHAR(50)
- chunk_size, chunk_overlap: INTEGER
- embedding_model, embedding_model_version: VARCHAR
- embedding_dimension: INTEGER

**parent_chunks** (3 fields):
- content_hash, embedding_model, embedding_model_version

**child_chunks** (3 fields):
- embedding_model, embedding_model_version
- index_alias: VARCHAR(50), indexed (for blue-green)

## Steps

1. Create alembic migration 0015_knowledge_metadata.py
2. Update SQLAlchemy models (Document, ParentChunk, ChildChunk)
3. Run `alembic upgrade head`
4. Verify columns exist

## Acceptance
- [ ] Migration runs without error
- [ ] 15 new columns exist
- [ ] index_alias on child_chunks for IndexAlias
- [ ] Old tests still pass (regression)

## Reference
- Harness v2 sec 7.1
- JavaGuide rag-knowledge-update.md
