---
skill_id: rag-index-alias
name: Add IndexAlias for blue-green embedding switch
description: Implement IndexAlias with create_new / switch / rollback / cleanup methods. Dry-run before actual switch, 7-day rollback window.
tags: [rag, deployment, blue-green, embedding]
version: 1.0
estimated_time: 1-2 days
prerequisites:
  - Knowledge metadata migration done
  - child_chunks.index_alias column exists
---

# Add Index Alias (Blue-Green)

## Goal
Allow switching embedding model (e.g. bge-large-zh -> bge-m3) without service downtime. Like Milvus Alias.

## API

```python
class IndexAlias:
    DEFAULT_ALIAS = "prod"
    ROLLBACK_WINDOW_DAYS = 7

    async def create_new(self, new_index, embedding_model=None)
    async def switch(self, new_index, old_index, dry_run=True)
    async def rollback(self)
    async def cleanup_old(self, keep_days=7)
    async def _count_index(self, alias) -> int
    def get_history(self) -> list
```

## Steps

1. Create app/rag/index_alias.py with IndexAlias class
2. Add API endpoints in app/server/api.py:
   - GET /api/rag/index_alias (status)
   - POST /api/rag/index_alias/create
   - POST /api/rag/index_alias/switch (with dry_run flag)
   - POST /api/rag/index_alias/rollback
3. Test with dry_run=True (safe)
4. Document the actual switch procedure:
   - build new embedding with new model
   - index all docs into new index (index_alias='index_v2')
   - eval on test set, compare to current
   - switch alias (UPDATE child_chunks SET index_alias='index_v2' WHERE ...)
   - keep old index for 7 days (rollback window)

## Acceptance
- [ ] IndexAlias class implements 5 methods
- [ ] create_new returns count
- [ ] switch with dry_run=True doesn't modify DB
- [ ] switch with dry_run=False actually changes index_alias
- [ ] rollback restores previous alias
- [ ] API endpoints work

## Reference
- Harness v2 sec 7.3
- Milvus Alias design
