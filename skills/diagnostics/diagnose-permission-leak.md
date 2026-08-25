---
skill_id: diagnose-permission-leak
name: Diagnose permission leak (cross-tenant data exposure)
trigger: 安全测试发现越权 OR tenant 隔离测试失败
estimated_time: 1h
---

# Diagnose Permission Leak

## Symptom
用户能查到其他 tenant 的文档, 或者 audience=staff 的内容被 user 看到.

## Diagnosis Steps

1. **看 PrefilterPlugin**: tenant_id 是否从 ctx 正确传入?
2. **看 v2_engine.retrieve**: audience_filter 是否真的传到了 pgvector?
3. **看 Permission 矩阵**: ROLE_PERMISSION_MATRIX 是否正确?
4. **看 API 层**: chat_handler 是否校验了 user role?
5. **看 JWT**: role claim 是否被篡改?
6. **看 is_published**: 未发布的 doc 是否被检索到?

## Common Fixes

| 问题 | 修法 |
|---|---|
| Prefilter 漏掉 audience | 在 PrefilterPlugin 强制设 default audience_filter |
| retrieve 漏掉 include_unpublished | 测试时正确传参, 生产禁止 include_unpublished=True |
| Permission 矩阵漏角色 | 补 ROLE_PERMISSION_MATRIX |
| JWT role 被改 | 用 jose 库的 verify, 不要手动 decode |
| 未发布 doc 被检索 | v2_engine 默认 include_unpublished=False (已修) |
| tenant_id 不一致 | PipelineContext 加 tenant_id, 优先 ctx.tenant_id (已修) |

## Reference
- Harness v2 sec 4.3 (Quality Gate)
- 多租户隔离设计
