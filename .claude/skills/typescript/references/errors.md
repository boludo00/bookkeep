# TypeScript Error Handling Reference

## Contents
- Type Guard Patterns
- Error Handling in API Calls
- Null Handling Strategies
- Common Type Errors
- Debugging Type Issues

## Type Guard Patterns

### Filter with Type Narrowing

```typescript
// src/components/books/BookCard.tsx
const statusSource = requestStatus || existingRequests;

// Type guard in filter predicate
const requestStatuses = statusSource
  ? [statusSource.ebook, statusSource.audiobook].filter((value): value is string => !!value)
  : [];

// Result: requestStatuses is string[] (not (string | null | undefined)[])
```

### Custom Type Guard Function

```typescript
// Type guard for checking if value exists
function isDefined<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

// Usage
const books = rawBooks.filter(isDefined); // Book[] instead of (Book | null)[]
```

## Error Handling in API Calls

### API Request Error Handling

```typescript
// src/lib/api.ts
async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...options, headers });

  // Handle 401 - token refresh
  if (response.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest<T>(endpoint, options, false);
    }
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  // Handle other errors
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.detail || error.message || `API request failed: ${response.status}`);
  }

  // Handle empty responses
  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return JSON.parse(await response.text());
}
```

### TanStack Query Error Typing

```typescript
// Explicit error type in useQuery
const { data, error } = useQuery<DownloadTask[], Error>({
  queryKey: ['download-tasks'],
  queryFn: () => downloadsApi.getTasks(),
  retry: false,
});

// error is typed as Error | null
if (error) {
  console.error(error.message);
}
```

### Mutation Error Handling

```typescript
// src/pages/Downloads.tsx
const importMutation = useMutation({
  mutationFn: (taskId: number) => downloadsApi.importDownload(taskId),
  onSuccess: (data) => {
    toast.success('Import successful', { description: data.message });
    queryClient.invalidateQueries({ queryKey: ['download-tasks'] });
  },
  onError: (err: Error) => {
    toast.error('Import failed', { description: err.message });
  },
});
```

## Null Handling Strategies

### Context with Undefined Check

```typescript
// src/contexts/UserContext.tsx
const UserContext = createContext<UserContextType | undefined>(undefined);

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context; // Type is UserContextType, not UserContextType | undefined
}
```

### Nullish Coalescing for Defaults

```typescript
// GOOD - Clear default handling
const ebookAvailable = book.ebookAvailable ?? false;
const isAdmin = user?.is_admin ?? false;

// BAD - Logical OR can hide false/0 values
const count = book.pageCount || 100; // 0 pages becomes 100!
```

### Optional Chaining Appropriately

```typescript
// GOOD - Property genuinely optional
const seriesName = book.series?.name;

// BAD - Defensive coding hiding bugs
const title = response?.data?.book?.title ?? 'Unknown';
// If response.data.book should always exist, don't use ?.
```

## Common Type Errors

### Error: Property does not exist on type

```typescript
// Problem
const title = book.tittle; // Error: Property 'tittle' does not exist

// Fix: Check the interface definition in src/types/book.ts
const title = book.title;
```

### Error: Argument of type X is not assignable to Y

```typescript
// Problem
const status = 'active'; // type: string
const request: BookRequest = { status }; // Error: string not assignable to union

// Fix: Use const assertion or explicit type
const status = 'pending' as const;
// OR
const status: BookRequest['status'] = 'pending';
```

### Error: Object is possibly undefined

```typescript
// Problem (with strictNullChecks enabled elsewhere)
const name = user.name; // Error: user might be null

// Fix 1: Guard clause
if (!user) return null;
const name = user.name; // Safe

// Fix 2: Non-null assertion (use sparingly)
const name = user!.name;

// Fix 3: Default value
const name = user?.name ?? 'Anonymous';
```

## Debugging Type Issues

### Hover for Inferred Types

In VS Code, hover over a variable to see its inferred type. If it shows `any`, add explicit typing.

### Check Type Origin

```typescript
// Use Go to Definition (F12) on types to find source
import type { Book } from '@/types/book';
//           ^^^^^ F12 here shows the interface
```

### Isolate Generic Issues

```typescript
// If a generic call fails, break it down
const result = await apiRequest<{ books: Book[] }>('/api/books');

// Check each part:
// 1. Does apiRequest accept this type parameter?
// 2. Does the response match { books: Book[] }?
// 3. Is Book imported correctly?
```

### WARNING: Suppressing Errors with `any`

**The Problem:**

```typescript
// BAD - Hides the real issue
const data = response as any;
console.log(data.whatever); // No type checking
```

**The Fix:** Understand why the error occurs. Usually it's:
1. Missing type definition → Add interface
2. Incorrect data shape → Fix the type or the data
3. Null/undefined → Add proper guards