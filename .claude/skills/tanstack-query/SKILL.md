I've created the TanStack Query skill with all required files. Here's a summary of what was generated:

## Generated Files

**`SKILL.md`** (~75 lines)
- Quick overview of TanStack Query v5 usage in this codebase
- Basic query and mutation examples from actual project code
- Key concepts table (query keys, enabled, staleTime, etc.)
- Common patterns like dependent queries and smart polling
- Links to reference files and related skills

**`references/patterns.md`** (~150 lines)
- Query key conventions with real examples from the codebase
- Query configuration patterns for different data types (static, frequently updated, immutable)
- Smart refetch interval function pattern
- Mutation patterns (basic, sequential with mutateAsync, dynamic create/update)
- Cache invalidation strategies (exact, prefix, cascade, full clear)
- Anti-patterns with WARNING headers:
  - useState + useEffect for server data
  - Missing `enabled` for conditional queries
  - Invalidating before mutation completes
  - Over-aggressive refetching

**`references/workflows.md`** (~145 lines)
- Creating new query hooks workflow with checklist
- Implementing polling with exponential backoff (from `useAvailabilityPolling`)
- Mutation workflows (delete with confirmation, multi-step chains)
- Dependent query chains (two-stage fetch, batch queries)
- Error handling patterns (display, auth with no retry, graceful fallback)
- Validation loop for mutations

All examples are drawn from the actual Bookkeep codebase (`src/hooks/useHardcoverBooks.ts`, `src/pages/BookDetails.tsx`, `src/components/books/RequestDialog.tsx`, etc.) and follow the established patterns in the project.