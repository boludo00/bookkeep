# Data Fetching Reference

## Contents
- TanStack Query Configuration
- API Client Structure
- Query Patterns
- Mutation Patterns
- Batch Fetching
- Token Refresh

## TanStack Query Configuration

From `src/App.tsx:42-49`:

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,           // 30 seconds
      refetchOnWindowFocus: false, // Don't refetch when tab regains focus
    },
  },
});
```

See the **tanstack-query** skill for advanced configuration.

## API Client Structure

All API calls go through `src/lib/api.ts`. The client handles:
- JWT token injection
- Automatic token refresh on 401
- Organized API modules

```tsx
// src/lib/api.ts structure
export const hardcoverApi = {
  search: (query, limit) => apiRequest(`/api/hardcover/search?query=${query}`),
  getTrending: (limit) => apiRequest(`/api/hardcover/trending?limit=${limit}`),
};

export const requestsApi = {
  getAll: (skip, limit, status) => apiRequest(`/api/requests/?skip=${skip}`),
  create: (data) => apiRequest('/api/requests/', { method: 'POST', body: data }),
  getByHardcoverId: (id) => apiRequest(`/api/requests/by-hardcover/${id}`),
};

export const booksApi = { /* ... */ };
export const readarrApi = { /* ... */ };
```

## Query Patterns

### Basic Query

```tsx
const { data, isLoading, error } = useQuery({
  queryKey: ['hardcover', 'trending', limit],
  queryFn: () => hardcoverApi.getTrending(limit),
  staleTime: 24 * 60 * 60 * 1000,  // 24 hours
});
```

### Conditional Query

```tsx
const { data } = useQuery({
  queryKey: ['book-requests', hardcoverId],
  queryFn: () => requestsApi.getByHardcoverId(hardcoverId),
  enabled: !!hardcoverId && dialogOpen,  // Only fetch when needed
  staleTime: 60_000,
});
```

### Dependent/Chained Query

```tsx
const booksQuery = useQuery({
  queryKey: ['books'],
  queryFn: fetchBooks,
});

const availabilityQuery = useQuery({
  queryKey: ['availability', booksQuery.data?.map(b => b.id)],
  queryFn: () => fetchAvailability(booksQuery.data!),
  enabled: !!booksQuery.data?.length,  // Wait for books
});
```

## Mutation Patterns

From `src/components/books/RequestDialog.tsx:150-158`:

```tsx
const queryClient = useQueryClient();

const createRequestMutation = useMutation({
  mutationFn: async ({ bookId, format }: { bookId: number; format: string }) => {
    return requestsApi.create({ book_id: bookId, format, notes });
  },
});

const handleSubmit = async () => {
  await createRequestMutation.mutateAsync({ bookId, format });
  
  // Invalidate related queries
  queryClient.invalidateQueries({ queryKey: ['requests'] });
  queryClient.invalidateQueries({ queryKey: ['book-requests', hardcoverId] });
};
```

## Batch Fetching

When displaying many items that need status, batch the requests:

From `src/pages/Discover.tsx`:

```tsx
// Collect all hardcover IDs from multiple lists
const discoverHardcoverIds = Array.from(new Set([
  ...trendingBooks.map(b => b.hardcoverId),
  ...popularBooks.map(b => b.hardcoverId),
])).filter(Boolean);

// Single batch request instead of N individual requests
const { data: requestStatuses } = useQuery({
  queryKey: ['requests', 'by-hardcover', 'batch', discoverHardcoverIds],
  queryFn: () => requestsApi.getByHardcoverBatch(discoverHardcoverIds),
  enabled: discoverHardcoverIds.length > 0,
});

// Create lookup map for O(1) access
const statusMap = new Map(
  requestStatuses?.results.map(item => [item.hardcover_id, item])
);
```

## Token Refresh

From `src/lib/api.ts:112-145`:

```tsx
async function apiRequest<T>(endpoint: string, options = {}, retry = true): Promise<T> {
  const headers = { 'Content-Type': 'application/json' };
  const accessToken = getAccessToken();
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, headers });

  // Handle 401 - try to refresh token
  if (response.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest<T>(endpoint, options, false);  // Retry with new token
    }
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) throw new Error(await response.json().detail);
  return response.json();
}
```

## WARNING: useEffect for Data Fetching

**The Problem:**

```tsx
// BAD - Anti-pattern in this codebase
useEffect(() => {
  fetch('/api/books').then(r => r.json()).then(setData);
}, []);
```

**Why This Breaks:**
1. Race conditions if component unmounts
2. No caching - fetches on every mount
3. No loading/error states without boilerplate
4. No automatic refetching

**The Fix:** Always use TanStack Query:

```tsx
// GOOD - Use useQuery
const { data, isLoading, error } = useQuery({
  queryKey: ['books'],
  queryFn: () => booksApi.getAll(),
});