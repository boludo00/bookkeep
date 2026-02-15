#!/bin/bash
# UserPromptSubmit hook for skill-aware responses

cat <<'EOF'
REQUIRED: SKILL LOADING PROTOCOL

Before writing any code, complete these steps in order:

1. SCAN each skill below and decide: LOAD or SKIP (with brief reason)
   - react
   - typescript
   - tailwind
   - frontend-design
   - tanstack-query
   - vite
   - shadcn-ui
   - fastapi
   - python
   - sqlalchemy
   - postgresql
   - alembic
   - apscheduler
   - redis
   - pytest

2. For every skill marked LOAD → immediately invoke Skill(name)
   If none need loading → write "Proceeding without skills"

3. Only after step 2 completes may you begin coding.

IMPORTANT: Skipping step 2 invalidates step 1. Always call Skill() for relevant items.

Sample output:
- react: LOAD - building components
- typescript: SKIP - not needed for this task
- tailwind: LOAD - building components
- frontend-design: SKIP - not needed for this task

Then call:
> Skill(react)
> Skill(tailwind)

Now implementation can begin.
EOF
