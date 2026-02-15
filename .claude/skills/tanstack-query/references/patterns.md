# TanStack Query Patterns Reference

## Contents
- Query Key Conventions
- Query Configuration Patterns
- Mutation Patterns
- Cache Invalidation Strategies
- Anti-Patterns

---

## Query Key Conventions

This codebase uses **hierarchical array keys** with domain-based organization:

```typescript
// Format: ['domain', 'resource', ...params]
['hardcover', 'trending', limit]           // Hardcover API trending
['hardcover', 'search', query, limit]      // Search results
['requests', 'by-hardcover', hardcoverId]  // Request by Hardcover ID
['book', 'by-hardcover', hardcoverId]      // Book lookup
['download-tasks', filterState]            // Downloads list
```

### Key Design Rules

1. **First segment** = domain/feature (`hardcover`, `requests`, `book`)
2. **Second segment** = operation/resource type (`trending`, `search`, `by-hardcover`)
3. **Remaining segments** = parameters affecting cache identity

---

## Query Configuration Patterns

### Pattern: Long-Lived Static Data

```typescript
// src/hooks/useHardcoverBooks.ts:66-75
export function useTrendingBooks(limit: number = 12) {
  return useQuery({
    queryKey: ['hardcover', 'trending', limit],
    queryFn: async () => {
      const data = await getTrendingBooks(limit);
      return transformBooks(data.books || []);
    },
    staleTime: 24 * 60 * 60 * 1000,  // 24 hours - data rarely changes
    gcTime: 24 * 60 * 60 * 1000,     // Keep in cache 24 hours
  });
}
```

### Pattern: Frequently Updated Data with Visibility-Based Polling

```typescript
// src/pages/BookDetails.tsx:46-54
const { data: requestStatus } = useQuery({
  queryKey: ['requests', 'by-hardcover', hardcoverId],
  queryFn: () => requestsApi.getByHardcoverId(hardcoverId as number),
  enabled: hasHardcoverId,
  staleTime: 15 * 1000,                              // 15 seconds
  refetchOnMount: true,                              // Always fresh on mount
  refetchInterval: hasHardcoverId && isVisible ? 30_000 : false,  // Pause when hidden
  gcTime: 5 * 60 * 1000,
});
```

### Pattern: Immutable Data (Never Changes)

```typescript
// src/hooks/useHardcoverBooks.ts:164-180
export function useBookPrompts(bookId: number | undefined) {
  return useQuery({
    queryKey: ['hardcover', 'book-prompts', bookId],
    queryFn: () => getBookPrompts(bookId!),
    enabled: Number.isFinite(bookId),
    staleTime: Infinity,           // Never refetch - prompts don't change
    gcTime: 24 * 60 * 60 * 1000,   // But garbage collect after 24h
  });
}
```

### Pattern: Smart Refetch Interval Function

```typescript
// src/pages/Downloads.tsx - only poll when active downloads exist
refetchInterval: (query) => {
  if (!isVisible) return false;
  const data = query.state.data;
  if (!data) return 5000;  // Poll until first data arrives
  const hasActive = data.some((t: DownloadTask) =>
    ['queued', 'downloading', 'checking'].includes(t.state)
  );
  return hasActive ? 5000 : false;  // Stop polling when all complete
},
```

---

## Mutation Patterns

### Pattern: Basic Mutation with Toast Feedback

```typescript
// src/pages/Requests.tsx
const deleteMutation = useMutation({
  mutationFn: () => requestsApi.delete(Number(request.id)),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['requests'] });
    toast.success('Request deleted');
  },
  onError: (error: Error) => {
    toast.error('Failed to delete request', { description: error.message });
  },
});
```

### Pattern: Sequential Mutations with mutateAsync

```typescript
// src/components/books/RequestDialog.tsx:160-198
const handleSubmit = async () => {
  try {
    // Step 1: Ensure book exists (may create it)
    const bookId = await ensureBookMutation.mutateAsync();

    // Step 2: Create request(s)
    for (const format of formatsToRequest) {
      await createRequestMutation.mutateAsync({ bookId, format });
    }

    // Step 3: Invalidate after ALL mutations complete
    queryClient.invalidateQueries({ queryKey: ['requests'] });
    queryClient.invalidateQueries({ queryKey: ['book-requests', book.hardcoverId] });

    toast.success('Request submitted!');
    onOpenChange(false);
  } catch (error: any) {
    toast.error('Request failed', { description: error.message });
  }
};
```

### Pattern: Dynamic Create/Update Mutation

```typescript
// src/pages/Settings.tsx - same mutation handles create and update
const saveServerMutation = useMutation({
  mutationFn: (server: any) => {
    if (editingServer) {
      return readarrApi.update(editingServer.id, server);
    }
    return readarrApi.create(server);
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['readarr-servers'] });
    toast.success(`Server ${editingServer ? 'updated' : 'created'}!`);
  },
});
```

---

## Cache Invalidation Strategies

### Exact Key Invalidation

```typescript
queryClient.invalidateQueries({ queryKey: ['requests'] });
```

### Prefix Invalidation (All Matching Keys)

```typescript
// Invalidates: ['requests', 'by-hardcover', 123], ['requests', 'by-hardcover', 456], etc.
queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });
```

### Cascade Invalidation on State Change

```typescript
// src/hooks/useAvailabilityPolling.ts:88-108
if (newlyAvailable.length > 0) {
  // Invalidate availability
  queryClient.invalidateQueries({ queryKey: ['readarr', 'availability'] });

  // Invalidate requests
  queryClient.invalidateQueries({ queryKey: ['requests'] });
  queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });

  // Invalidate series if applicable
  if (seriesId) {
    queryClient.invalidateQueries({ queryKey: ['series', seriesId] });
  }
}
```

### Full Cache Clear (Logout)

```typescript
// src/contexts/UserContext.tsx:32-37
const logout = () => {
  authApi.logout();
  setIsLoggedIn(false);
  queryClient.clear();  // Wipe entire cache on logout
  window.location.href = '/login';
};
```

---

## Anti-Patterns

### WARNING: useState + useEffect for Server Data

**The Problem:**

```typescript
// BAD - race conditions, no caching, memory leaks
const [data, setData] = useState(null);
const [loading, setLoading] = useState(true);

useEffect(() => {
  fetch('/api/books')
    .then(r => r.json())
    .then(setData)
    .finally(() => setLoading(false));
}, []);
```

**Why This Breaks:**
1. No request deduplication - multiple components fetch same data
2. Race conditions - fast navigation causes stale data overwrites
3. Memory leaks - setState after unmount
4. No caching - every mount triggers network request
5. No retry logic for transient failures

**The Fix:**

```typescript
// GOOD - use useQuery
const { data, isLoading } = useQuery({
  queryKey: ['books'],
  queryFn: () => booksApi.getAll(),
});
```

### WARNING: Missing `enabled` for Conditional Queries

**The Problem:**

```typescript
// BAD - throws error when hardcoverId is undefined
const { data } = useQuery({
  queryKey: ['requests', hardcoverId],
  queryFn: () => requestsApi.getByHardcoverId(hardcoverId),
});
```

**The Fix:**

```typescript
// GOOD - wait for data to be available
const { data } = useQuery({
  queryKey: ['requests', hardcoverId],
  queryFn: () => requestsApi.getByHardcoverId(hardcoverId!),
  enabled: !!hardcoverId,  // Only fetch when ID exists
});
```

### WARNING: Invalidating Before Mutation Completes

**The Problem:**

```typescript
// BAD - fire-and-forget mutation
mutation.mutate(data);
queryClient.invalidateQueries({ queryKey: ['items'] });  // Runs immediately!
```

**The Fix:**

```typescript
// GOOD - invalidate in onSuccess or use await
const mutation = useMutation({
  mutationFn: updateItem,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['items'] });
  },
});

// OR with mutateAsync
await mutation.mutateAsync(data);
queryClient.invalidateQueries({ queryKey: ['items'] });
```

### WARNING: Over-Aggressive Refetching

**The Problem:**

```typescript
// BAD - refetches on every focus, wastes bandwidth
useQuery({
  queryKey: ['trending'],
  queryFn: fetchTrending,
  // Default refetchOnWindowFocus: true
});
```

**The Fix:**

The codebase sets `refetchOnWindowFocus: false` globally in `src/App.tsx:42-49`. For data that changes frequently, use explicit `refetchInterval` with page visibility checks.

```typescript
refetchInterval: isVisible ? 30_000 : false,  // Pause when tab hidden
```
