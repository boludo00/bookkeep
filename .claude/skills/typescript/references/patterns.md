# TypeScript Patterns Reference

## Contents
- Relaxed Strict Mode Strategy
- Component Props Patterns
- API Response Typing
- Union Types for Status
- Const Assertions
- Generic Patterns
- Anti-Patterns

## Relaxed Strict Mode Strategy

This project intentionally disables strict mode in `tsconfig.json`:

```json
{
  "compilerOptions": {
    "noImplicitAny": false,
    "strictNullChecks": false,
    "noUnusedLocals": false
  }
}
```

**Why:** Enables rapid development while maintaining type safety at critical boundaries (APIs, props, contexts).

## Component Props Patterns

### Named Props Interface

```typescript
// GOOD - Clear, named interface
interface BookCardProps {
  book: Book;
  status?: 'available' | 'pending' | 'none';
  showRating?: boolean;
}

export const BookCard = memo(function BookCard({
  book,
  status = 'none',
  showRating = true,
}: BookCardProps) {
  // ...
});
```

### WARNING: Inline Props Types

**The Problem:**

```typescript
// BAD - Inline object type
export const BookCard = ({ book, status }: { book: Book; status?: string }) => {
  // ...
};
```

**Why This Breaks:**
1. Cannot be reused or extended
2. Hard to document with JSDoc
3. Makes component signatures unreadable

**The Fix:** Always define a named `Props` interface above the component.

## API Response Typing

### Generic API Client

```typescript
// src/lib/api.ts
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  // ...
  return JSON.parse(text);
}

// Usage - explicit type parameter
export const hardcoverApi = {
  search: (query: string, limit: number = 20) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/search?query=${encodeURIComponent(query)}&limit=${limit}`),

  getEditions: (bookId: number) =>
    apiRequest<{
      default_cover_edition_id: number | null;
      editions: Array<{
        id: number;
        title?: string;
        reading_format?: string;
      }>;
    }>(`/api/hardcover/editions/${bookId}`),
};
```

### WARNING: Untyped API Responses

**The Problem:**

```typescript
// BAD - No type safety on response
const data = await fetch('/api/books').then(r => r.json());
console.log(data.books[0].tittle); // Typo not caught
```

**The Fix:**

```typescript
// GOOD - Type parameter enforces structure
const data = await apiRequest<{ books: Book[] }>('/api/books');
console.log(data.books[0].title); // Typo caught at compile time
```

## Union Types for Status

### String Literal Unions

```typescript
// src/types/book.ts
export interface BookRequest {
  format: 'ebook' | 'audiobook';
  status: 'pending' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found';
}
```

### Discriminated Status Records

```typescript
// Config objects with union key constraints
const statusConfig: Record<string, { 
  label: string; 
  variant: 'default' | 'secondary' | 'outline';
}> = {
  pending: { label: 'Pending', variant: 'secondary' },
  approved: { label: 'Approved', variant: 'default' },
  denied: { label: 'Denied', variant: 'outline' },
};
```

## Const Assertions

### Preserving Literal Types

```typescript
// Without as const - type widens to string
const format = 'ebook'; // type: string

// With as const - type stays literal
const format = 'ebook' as const; // type: 'ebook'

// Used when building objects for type-safe APIs
requests.push({
  hardcoverId: status.hardcover_id,
  format: 'ebook' as const, // Ensures format is 'ebook', not string
  readarrBookId: status.ebook_readarr_book_id || null,
});
```

### Action Type Constants

```typescript
// src/hooks/use-toast.ts
const actionTypes = {
  ADD_TOAST: "ADD_TOAST",
  UPDATE_TOAST: "UPDATE_TOAST",
  DISMISS_TOAST: "DISMISS_TOAST",
  REMOVE_TOAST: "REMOVE_TOAST",
} as const;

// Type becomes: "ADD_TOAST" | "UPDATE_TOAST" | "DISMISS_TOAST" | "REMOVE_TOAST"
type ActionType = typeof actionTypes[keyof typeof actionTypes];
```

## Generic Patterns

### Generic Map with Refs

```typescript
// src/hooks/useAvailabilityPolling.ts
const previousAvailabilityRef = useRef<Map<number, { ebook: boolean; audiobook: boolean }>>(new Map());

// Type-safe map operations
previousAvailabilityRef.current.set(item.hardcover_id, { ebook: true, audiobook: false });
const previous = previousAvailabilityRef.current.get(item.hardcover_id);
```

### ReturnType Utility

```typescript
// Infer return type from transformation function
export function transformHardcoverBook(hcBook: HardcoverBook) {
  return { id: String(hcBook.id), title: hcBook.title, /* ... */ };
}

// Use ReturnType to extract the shape
type TransformedBook = ReturnType<typeof transformHardcoverBook>;
```

## Anti-Patterns

### WARNING: Using `any` for API Responses

**When You Might Be Tempted:** When backend types change frequently or you're prototyping.

**The Problem:** Defeats TypeScript's purpose. Typos and missing properties go undetected.

**The Fix:** Define interfaces in `src/types/` or inline in the API module. Even partial typing is better than `any`.

### WARNING: Optional Chaining Overuse

**The Problem:**

```typescript
// BAD - Defensive coding hiding real bugs
const title = book?.data?.metadata?.title ?? 'Unknown';
```

**Why This Breaks:** Masks undefined access bugs. If `book.data` should always exist, make it non-optional.

**The Fix:** Model your types accurately. Use optional (`?`) only when the property is genuinely optional.