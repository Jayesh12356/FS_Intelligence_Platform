# CONTEXT_L9 — Semantic Intelligence + Collaboration

## What This Level Builds
Qdrant-powered semantic features + team collaboration layer.
Duplicate requirement detection, reusable requirement library,
comments, approval workflows, and full audit trail.

## Stack Used
Qdrant (full use) · PostgreSQL · LangGraph (search node)

## Build Order (6 prompts)

### Prompt 01 — Duplicate requirement detection
```
backend/app/pipeline/nodes/duplicate_node.py
  duplicate_node(state) -> state
  For each parsed section:
    Search qdrant fs_requirements for cosine similarity > 0.88
    If match found from a DIFFERENT FS document: flag as potential duplicate
  DuplicateFlag: section_id, similar_section_id, similar_fs_id, similarity_score
  GET /api/fs/{id}/duplicates
```

### Prompt 02 — Requirement library
```
backend/app/api/library_router.py
  When a requirement is approved + tasks generated:
    Auto-add to fs_library Qdrant collection
  GET /api/library/search?q= — semantic search in library
  GET /api/library/{id} — get a reusable requirement
  POST /api/fs/{id}/suggestions — suggest similar requirements
    from library while user is writing a new FS
```

### Prompt 03 — Comments + collaboration
```
db/models.py — add:
  FSComment: id, fs_id, section_id, user_id, text, resolved, created_at
  FSMention: id, comment_id, mentioned_user_id

backend/app/api/collab_router.py:
  POST /api/fs/{id}/sections/{section_id}/comments
  GET /api/fs/{id}/comments
  PATCH /api/fs/{id}/comments/{comment_id}/resolve
```

### Prompt 04 — Approval workflow
```
db/models.py — add:
  FSApproval: id, fs_id, approver_id, status (PENDING/APPROVED/REJECTED),
              comment, created_at

backend/app/api/approval_router.py:
  POST /api/fs/{id}/submit-for-approval
  POST /api/fs/{id}/approve
  POST /api/fs/{id}/reject
  GET /api/fs/{id}/approval-status
Pipeline: tasks only generated AFTER FS is approved
```

### Prompt 05 — Audit trail
```
db/models.py — add:
  AuditEvent: id, fs_id, user_id, event_type, payload_json, created_at
  event_types: UPLOADED, PARSED, ANALYZED, APPROVED, REJECTED,
               VERSION_ADDED, TASKS_GENERATED, EXPORTED

backend/app/api/audit_router.py:
  GET /api/fs/{id}/audit-log
Log every state change automatically via SQLAlchemy event listeners
```

### Prompt 06 — Frontend
```
Requirements library search page (/library)
Comment threads visible on section detail view
Approval status badge on document page
Audit log timeline on document page
Duplicate warning banner when similar requirements found
```

## Done When
- ✅ Duplicate detection flags cross-document similar requirements
- ✅ Requirement library grows with each approved FS
- ✅ Comments and approvals flow works
- ✅ Full audit log visible per document
- ✅ 43 L9 tests pass, 280 total (0 regressions)

## Status: COMPLETE

### Implementation Summary
- **DB Models**: 5 tables (duplicate_flags, fs_comments, fs_mentions, fs_approvals, audit_events) + 2 enums
- **Pipeline**: duplicate_node added after traceability_node in analysis graph
- **Vector Store**: search_similar_sections, store_library_item, search_library functions
- **API**: 5 new routers (duplicate, library, collab, approval, audit) with 14 endpoints
- **Audit**: Automatic event logging in upload, parse, analyze, version, comment, approval flows
- **Frontend**: Library search page, Collaboration page (comments + approvals + audit timeline), duplicate warning banner, approval badge on document detail

