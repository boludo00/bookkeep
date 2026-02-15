# Hooks Reference

## Contents
- Custom Hook Patterns
- Chained Query Pattern
- Polling with Exponential Backoff
- Page Visibility Hook
- Common Errors

## Custom Hook Patterns

### Naming Convention

Hooks in `src/hooks/` follow the `use` prefix pattern with camelCase filenames:
- `useHardcoverBooks.ts` - Data fetching hooks
- `useAvailabilityPolling.ts` - Polling logic
- `usePageVisibility.ts` - Browser API wrapper

### Basic Query Hook

From `src/hooks/useHardcoverBooks.ts:138-148`:

```tsx
export function useBookSearch(query: string, limit = 20) {
  return useQuery({
    queryKey: ['hardcover', 'search', query, limit],
    queryFn: async () => {
      const data = await searchBooks(query, limit);
      return transformBooks(data.books || []);
    },
    enabled: query.length > 0,  // Don't fetch on empty string
    staleTime: 2 * 60 * 1000,
  });
}
```

## Chained Query Pattern

When you need to enrich data with a second API call, use dependent queries.

From `src/hooks/useHardcoverBooks.ts:66-88`:

```tsx
export function useTrendingBooks(limit = 12) {
  // Stage 1: Fetch base data
  const booksQuery = useQuery({
    queryKey: ['hardcover', 'trending', limit],
    queryFn: async () => {
      const data = await getTrendingBooks(limit);
      return transformBooks(data.books || []);
    },
    staleTime: 24 * 60 * 60 * 1000,  // 24 hours - metadata rarely changes
  });

  // Stage 2: Enrich with availability (depends on Stage 1)
  const enrichedQuery = useQuery({
    queryKey: ['hardcover', 'trending', limit, 'availability'],
    queryFn: () => enrichAvailability(booksQuery.data!),
    enabled: !!booksQuery.data && booksQuery.data.length > 0,
    staleTime: 5 * 60 * 1000,  // 5 minutes - availability changes more often
  });

  // Return enriched data with fallback
  return {
    ...booksQuery,
    data: enrichedQuery.data ?? booksQuery.data,
  };
}
```

**Why this pattern:**
- Avoids waterfall if availability API is slow
- Shows book covers immediately, enriches availability later
- Different `staleTime` for different data freshness needs

## Polling with Exponential Backoff

From `src/hooks/useAvailabilityPolling.ts`:

```tsx
export function useAvailabilityPolling({
  pendingRequests,
  enabled = true,
  seriesId,
}: AvailabilityPollingOptions) {
  const queryClient = useQueryClient();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(Date.now());
  const isVisible = usePageVisibility();

  useEffect(() => {
    if (!enabled || pendingRequests.length === 0 || !isVisible) {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      return;
    }

    const getPollingInterval = () => {
      const elapsedMinutes = (Date.now() - startTimeRef.current) / 1000 / 60;
      if (elapsedMinutes < 5) return 60_000;       // 60s for first 5 min
      if (elapsedMinutes < 15) return 3 * 60_000;  // 3 min for 5-15 min
      return 5 * 60_000;                            // 5 min after
    };

    const scheduleNextCheck = () => {
      timeoutRef.current = setTimeout(async () => {
        await checkAvailability();
        scheduleNextCheck();  // Chain, don't use setInterval
      }, getPollingInterval());
    };

    checkAvailability();
    scheduleNextCheck();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [enabled, pendingRequests, isVisible]);
}
```

**Key points:**
- Use chained `setTimeout`, NOT `setInterval` (avoids stacking)
- Pause polling when tab is hidden (battery optimization)
- Exponential backoff reduces server load over time

## Page Visibility Hook

From `src/hooks/usePageVisibility.ts`:

```tsx
export function usePageVisibility(): boolean {
  const [isVisible, setIsVisible] = useState(!document.hidden);

  useEffect(() => {
    const handler = () => setIsVisible(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  return isVisible;
}
```

**Use for:** Pausing polling, animations, or expensive operations when tab is backgrounded.

## WARNING: Missing Dependency Array

**The Problem:**

```tsx
// BAD - Missing isVisible in dependencies
useEffect(() => {
  if (!isVisible) return;
  startPolling();
}, [pendingRequests]);  // isVisible missing!
```

**Why This Breaks:**
1. Stale closure captures old `isVisible` value
2. Polling continues when tab should pause
3. Wastes battery and bandwidth

**The Fix:**

```tsx
// GOOD - All dependencies included
useEffect(() => {
  if (!isVisible) return;
  startPolling();
}, [pendingRequests, isVisible]);
```

## WARNING: useEffect for Data Fetching

**The Problem:**

```tsx
// BAD - Anti-pattern
const [data, setData] = useState(null);
useEffect(() => {
  fetch('/api/books').then(r => r.json()).then(setData);
}, []);
```

**Why This Breaks:** Race conditions, no caching, memory leaks on unmount.

**The Fix:** Use TanStack Query. See the **tanstack-query** skill for patterns.