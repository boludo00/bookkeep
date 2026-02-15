# Performance Reference

## Contents
- Code Splitting with Lazy Loading
- Memoization Patterns
- Query Optimization
- Polling Optimization
- Image Loading

## Code Splitting with Lazy Loading

From `src/App.tsx`:

```tsx
import { Suspense, lazy } from 'react';

// Static imports for critical path only
import Login from '@/pages/Login';
import NotFound from '@/pages/NotFound';

// Lazy-load all other pages
const Discover = lazy(() => import('@/pages/Discover'));
const Browse = lazy(() => import('@/pages/Browse'));
const BookDetails = lazy(() => import('@/pages/BookDetails'));
const Settings = lazy(() => import('@/pages/Settings'));
// ... 11 more pages

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AuthWrapper />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Discover />} />
              {/* ... */}
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  </QueryClientProvider>
);
```

**Key points:**
- Keep Login as static import (critical for first load)
- Wrap lazy routes in single `Suspense` at route level
- Each page becomes a separate chunk

## Memoization Patterns

### memo() for Card Grids

```tsx
// GOOD - Prevents re-render when parent updates
export const BookCard = memo(function BookCard({ book, status }: BookCardProps) {
  return <div>{/* ... */}</div>;
});
```

### When to Avoid useMemo/useCallback

```tsx
// BAD - Premature optimization
const formattedDate = useMemo(() => formatDate(book.publishedDate), [book.publishedDate]);

// GOOD - Just compute it
const formattedDate = formatDate(book.publishedDate);
```

Only use `useMemo` for:
- Expensive calculations (filtering large arrays, complex transforms)
- Reference stability for props to memoized children

## Query Optimization

### Appropriate staleTime

```tsx
// Metadata rarely changes - 24 hours
{ staleTime: 24 * 60 * 60 * 1000 }

// Availability changes more often - 5 minutes
{ staleTime: 5 * 60 * 1000 }

// User-specific data - 5 minutes
{ staleTime: 5 * 60 * 1000 }

// Search results - 2 minutes
{ staleTime: 2 * 60 * 1000 }
```

### Batch Requests

```tsx
// BAD - N+1 queries
books.map(book => (
  <BookCard
    key={book.id}
    status={useQuery(['status', book.id])} // Query per card!
  />
));

// GOOD - Batch fetch once, pass down
const { data: statusMap } = useQuery({
  queryKey: ['status', 'batch', bookIds],
  queryFn: () => requestsApi.getByHardcoverBatch(bookIds),
});

books.map(book => (
  <BookCard key={book.id} status={statusMap.get(book.id)} />
));
```

## Polling Optimization

### Exponential Backoff

From `src/hooks/useAvailabilityPolling.ts`:

```tsx
const getPollingInterval = () => {
  const elapsed = (Date.now() - startTime) / 1000 / 60;
  if (elapsed < 5) return 60_000;       // 1 min for first 5 min
  if (elapsed < 15) return 3 * 60_000;  // 3 min for 5-15 min
  return 5 * 60_000;                     // 5 min after
};
```

### Pause When Hidden

```tsx
const isVisible = usePageVisibility();

useEffect(() => {
  if (!isVisible) {
    clearTimeout(timeoutRef.current);
    return;
  }
  // Start polling when visible
}, [isVisible]);
```

## Image Loading

```tsx
<img
  src={book.cover}
  alt={book.title}
  loading="lazy"  // Browser-native lazy loading
  className="h-full w-full object-cover"
/>
```

## WARNING: Inline Objects in Render

**The Problem:**

```tsx
// BAD - New object every render, breaks memo
<BookCard style={{ margin: 8 }} config={{ showRating: true }} />
```

**The Fix:**

```tsx
// GOOD - Stable references
const cardStyle = { margin: 8 };
const cardConfig = { showRating: true };

<BookCard style={cardStyle} config={cardConfig} />
```

Or use Tailwind classes instead of style objects.

## WARNING: Missing Query Keys

**The Problem:**

```tsx
// BAD - Same query key for different params
useQuery({ queryKey: ['books'], queryFn: () => fetchBooks(category) });
```

**Why This Breaks:** Different categories return same cached data.

**The Fix:**

```tsx
// GOOD - Include all params in query key
useQuery({
  queryKey: ['books', category, limit],
  queryFn: () => fetchBooks(category, limit),
});