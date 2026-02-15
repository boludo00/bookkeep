# TanStack Query Workflows Reference

## Contents
- Creating a New Query Hook
- Implementing Polling with Exponential Backoff
- Handling Mutations with Optimistic Updates
- Dependent Query Chains
- Error Handling Patterns

---

## Creating a New Query Hook

### Workflow Checklist

Copy this checklist and track progress:
- [ ] Step 1: Add API function to `src/lib/api.ts`
- [ ] Step 2: Create hook in `src/hooks/` with proper query key
- [ ] Step 3: Set appropriate `staleTime` based on data volatility
- [ ] Step 4: Add `enabled` condition if parameters may be undefined
- [ ] Step 5: Use hook in component with loading/error states

### Example: Complete Hook Implementation

```typescript
// Step 1: API function in src/lib/api.ts
export const myApi = {
  getItem: (id: number) =>
    apiRequest<MyItem>(`/api/items/${id}`),
};

// Step 2: Hook in src/hooks/useMyItem.ts
import { useQuery } from '@tanstack/react-query';
import { myApi } from '@/lib/api';

export function useMyItem(itemId: number | undefined) {
  return useQuery({
    queryKey: ['items', itemId],
    queryFn: () => myApi.getItem(itemId!),
    enabled: !!itemId,
    staleTime: 5 * 60 * 1000,  // 5 minutes
  });
}

// Step 3: Usage in component
function ItemDetails({ id }: { id: number }) {
  const { data, isLoading, error } = useMyItem(id);

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorDisplay message={error.message} />;

  return <div>{data.name}</div>;
}
```

---

## Implementing Polling with Exponential Backoff

The codebase uses custom polling with exponential backoff in `src/hooks/useAvailabilityPolling.ts`. This is the pattern for long-running background checks.

### Pattern: Custom Polling Hook

```typescript
// src/hooks/useAvailabilityPolling.ts
export function useAvailabilityPolling({
  pendingRequests,
  enabled = true,
}: Options) {
  const queryClient = useQueryClient();
  const startTimeRef = useRef<number>(Date.now());
  const isVisible = usePageVisibility();

  useEffect(() => {
    if (!enabled || pendingRequests.length === 0 || !isVisible) return;

    let cancelled = false;

    const getPollingInterval = () => {
      const elapsedMinutes = (Date.now() - startTimeRef.current) / 1000 / 60;
      if (elapsedMinutes < 5) return 60 * 1000;      // 1 min for first 5 mins
      if (elapsedMinutes < 15) return 3 * 60 * 1000; // 3 min for 5-15 mins
      return 5 * 60 * 1000;                          // 5 min after 15 mins
    };

    const checkAndSchedule = async () => {
      if (cancelled) return;
      await checkAvailability();
      setTimeout(checkAndSchedule, getPollingInterval());
    };

    checkAndSchedule();
    return () => { cancelled = true; };
  }, [enabled, pendingRequests, isVisible]);
}
```

### Alternative: Simple refetchInterval

For simpler polling needs, use `refetchInterval`:

```typescript
const { data } = useQuery({
  queryKey: ['download-tasks'],
  queryFn: downloadsApi.getTasks,
  refetchInterval: (query) => {
    // Adaptive: only poll when active downloads exist
    const hasActive = query.state.data?.some(t =>
      ['downloading', 'queued'].includes(t.state)
    );
    return hasActive ? 5000 : false;
  },
});
```

---

## Handling Mutations with Optimistic Updates

### Workflow: Delete with Confirmation

```typescript
// src/pages/Requests.tsx pattern
function RequestRow({ request }: Props) {
  const queryClient = useQueryClient();
  const [isDeleting, setIsDeleting] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => requestsApi.delete(request.id),
    onMutate: () => {
      setIsDeleting(true);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      toast.success('Request deleted');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete', { description: error.message });
    },
    onSettled: () => {
      setIsDeleting(false);
    },
  });

  return (
    <Button
      onClick={() => deleteMutation.mutate()}
      disabled={isDeleting}
    >
      {isDeleting ? <Loader2 className="animate-spin" /> : 'Delete'}
    </Button>
  );
}
```

### Workflow: Multi-Step Mutation Chain

```typescript
// src/components/books/RequestDialog.tsx pattern
const handleSubmit = async () => {
  setIsSubmitting(true);

  try {
    // 1. Ensure prerequisite exists
    const bookId = await ensureBookMutation.mutateAsync();

    // 2. Perform main operations
    for (const format of formatsToRequest) {
      await createRequestMutation.mutateAsync({ bookId, format });
    }

    // 3. Invalidate ALL related queries after success
    queryClient.invalidateQueries({ queryKey: ['requests'] });
    queryClient.invalidateQueries({ queryKey: ['book-requests', hardcoverId] });

    toast.success('Success!');
    onClose();
  } catch (error: any) {
    toast.error('Failed', { description: error.message });
  } finally {
    setIsSubmitting(false);
  }
};
```

---

## Dependent Query Chains

### Pattern: Query Enrichment (Two-Stage Fetch)

```typescript
// src/hooks/useHardcoverBooks.ts:66-88
export function useTrendingBooks(limit: number = 12) {
  // Stage 1: Fetch core data
  const booksQuery = useQuery({
    queryKey: ['hardcover', 'trending', limit],
    queryFn: async () => {
      const data = await getTrendingBooks(limit);
      return transformBooks(data.books || []);
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  // Stage 2: Enrich with availability (depends on stage 1)
  const enrichedQuery = useQuery({
    queryKey: ['hardcover', 'trending', limit, 'availability'],
    queryFn: () => enrichAvailability(booksQuery.data!),
    enabled: !!booksQuery.data && booksQuery.data.length > 0,  // Wait for stage 1
    staleTime: 5 * 60 * 1000,  // Shorter - availability changes more often
  });

  // Return enriched data if available, otherwise raw data
  return {
    ...booksQuery,
    data: enrichedQuery.data ?? booksQuery.data,
  };
}
```

### Pattern: Batch Queries with useQueries

```typescript
// src/pages/Series.tsx
const seriesQueries = useQueries({
  queries: seriesList.map((series) => ({
    queryKey: ['series', series.id],
    queryFn: () => getSeriesBooks(series.id),
    enabled: Number.isFinite(series.id),
  })),
});
```

---

## Error Handling Patterns

### Pattern: Query Error Display

```typescript
// Common pattern in pages
const { data: book, isLoading, error } = useBookDetails(id);

if (error || !book) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh]">
      <h1 className="text-2xl font-bold">Book Not Found</h1>
      <p className="text-muted-foreground">
        {error?.message || "We couldn't find the book you're looking for."}
      </p>
      <Link to="/">
        <Button variant="outline">Go Back Home</Button>
      </Link>
    </div>
  );
}
```

### Pattern: Auth Query with No Retry

```typescript
// src/contexts/UserContext.tsx:22-30
const { data: user, isLoading } = useQuery({
  queryKey: ['currentUser'],
  queryFn: () => usersApi.getMe(),
  enabled: isLoggedIn,
  staleTime: 5 * 60 * 1000,
  retry: false,  // Don't retry 401s - redirect to login instead
});
```

### Pattern: Graceful Fallback for Non-Critical Data

```typescript
// Enrichment that fails gracefully
async function enrichAvailability(books: Book[]): Promise<Book[]> {
  try {
    const availability = await readarrApi.getAvailabilityBatch(ids);
    // ... enrich books
    return enrichedBooks;
  } catch {
    // Return original books if enrichment fails
    return books;
  }
}
```

---

## Validation Loop for Mutations

When a mutation might fail due to validation:

1. Attempt mutation
2. Handle error with specific feedback
3. Let user fix the issue
4. Retry mutation
5. Only invalidate queries on success

```typescript
const saveMutation = useMutation({
  mutationFn: saveItem,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['items'] });
    toast.success('Saved!');
  },
  onError: (error: Error) => {
    // Show specific error - don't invalidate
    toast.error('Validation failed', { description: error.message });
    // User fixes form and retries
  },
});
```
