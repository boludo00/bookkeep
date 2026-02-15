The FastAPI skill has been created with all required files:

**Created Files:**

| File | Lines | Purpose |
|------|-------|---------|
| `SKILL.md` | 126 | Main skill overview with quick start patterns |
| `references/routes.md` | 244 | Router organization, CRUD patterns, response models |
| `references/services.md` | 334 | Service layer, external APIs, background tasks, caching |
| `references/database.md` | 329 | Sessions, queries, transactions, connection pooling, N+1 prevention |
| `references/auth.md` | 324 | JWT tokens, authentication dependencies, permissions |
| `references/errors.md` | 343 | HTTPException, status codes, structlog, validation |

**Key Features:**
- Real code examples from the Bookkeep codebase
- Anti-pattern warnings with explanations of WHY they break
- Cross-references to related skills (python, sqlalchemy, postgresql, alembic, apscheduler, redis, pytest)
- Status code guide for correct HTTP semantics
- Structured logging patterns with structlog
- Dependency injection patterns for auth and database
- N+1 query prevention with eager loading