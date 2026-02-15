# TypeScript Modules Reference

## Contents
- Import Order Convention
- Path Alias Usage
- Module Organization
- API Client Structure
- Export Patterns

## Import Order Convention

Follow this order in all TypeScript files:

```typescript
// 1. React and external packages
import { useState, useEffect, memo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

// 2. Internal absolute imports (@/ alias)
import { Button } from '@/components/ui/button';
import { requestsApi, hardcoverApi } from '@/lib/api';
import { cn, formatRating } from '@/lib/utils';

// 3. Relative imports
import { BookCard } from './BookCard';
import { RequestDialog } from './RequestDialog';

// 4. Type-only imports (always last)
import type { Book, BookRequest } from '@/types/book';
import type { HardcoverBook } from '@/lib/hardcover';
```

## Path Alias Usage

The `@/` alias maps to `./src/` (configured in `tsconfig.json` and `vite.config.ts`):

```typescript
// GOOD - Use @/ for all src imports
import { Button } from '@/components/ui/button';
import { useUser } from '@/contexts/UserContext';
import type { Book } from '@/types/book';

// BAD - Relative paths for non-adjacent files
import { Button } from '../../../components/ui/button';
import { useUser } from '../../contexts/UserContext';
```

**When to use relative imports:** Only for files in the same directory or immediate subdirectory.

## Module Organization

### Project Structure

```
src/
├── components/
│   ├── ui/           # shadcn/ui primitives (kebab-case: button.tsx)
│   ├── books/        # Feature components (PascalCase: BookCard.tsx)
│   └── layout/       # Layout components
├── contexts/         # React contexts (UserContext.tsx)
├── hooks/            # Custom hooks (camelCase: useToast.ts)
├── lib/              # Utilities and clients
│   ├── api.ts        # Centralized API client
│   ├── hardcover.ts  # Data transformations
│   └── utils.ts      # Helper functions
├── pages/            # Route pages (PascalCase: BookDetails.tsx)
└── types/            # TypeScript interfaces
    └── book.ts       # Domain types
```

### File Naming Convention

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `BookCard.tsx` |
| UI primitives | kebab-case | `button.tsx`, `dialog.tsx` |
| Hooks | camelCase with `use` prefix | `useToast.ts` |
| Utilities | camelCase | `utils.ts` |
| Types | camelCase | `book.ts` |
| Contexts | PascalCase with `Context` suffix | `UserContext.tsx` |

## API Client Structure

### Modular API Organization

```typescript
// src/lib/api.ts - Organized by domain

// Core request function
async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  // JWT handling, error parsing
}

// Domain-specific API modules
export const hardcoverApi = {
  search: (query: string) => apiRequest<{ books: any[] }>(`/api/hardcover/search?query=${query}`),
  getDetails: (bookId: number) => apiRequest<{ books_by_pk: any }>(`/api/hardcover/details/${bookId}`),
  getTrending: (limit: number) => apiRequest<{ books: any[] }>(`/api/hardcover/trending?limit=${limit}`),
};

export const booksApi = {
  getAll: () => apiRequest<Array<any>>('/api/books/'),
  getById: (id: number) => apiRequest<any>(`/api/books/${id}`),
  create: (book: any) => apiRequest<any>('/api/books/', { method: 'POST', body: JSON.stringify(book) }),
};

export const requestsApi = {
  getAll: (skip?: number, limit?: number) => apiRequest<Array<any>>(`/api/requests/?skip=${skip}&limit=${limit}`),
  getByHardcoverId: (id: number) => apiRequest<{ ebook: string | null; audiobook: string | null }>(`/api/requests/by-hardcover/${id}`),
};
```

### Consuming API Modules

```typescript
// In components, import specific modules
import { hardcoverApi, requestsApi } from '@/lib/api';

// Use with TanStack Query
const { data } = useQuery({
  queryKey: ['hardcover', 'trending'],
  queryFn: () => hardcoverApi.getTrending(20),
});
```

## Export Patterns

### Named Exports (Preferred)

```typescript
// src/types/book.ts
export interface Book { /* ... */ }
export interface BookRequest { /* ... */ }
export interface RequestStatus { /* ... */ }

// Usage
import type { Book, BookRequest } from '@/types/book';
```

### Re-exports for Public API

```typescript
// src/lib/api.ts exports types alongside functions
export interface ApiUser { /* ... */ }
export interface LoginResponse { /* ... */ }

export const usersApi = { /* ... */ };
export const authApi = { /* ... */ };

// Consumers get types and functions from same import
import { usersApi, authApi, ApiUser } from '@/lib/api';
```

### WARNING: Circular Imports

**The Problem:**

```typescript
// api.ts imports from hardcover.ts
import { transformBook } from '@/lib/hardcover';

// hardcover.ts imports from api.ts
import { apiRequest } from '@/lib/api'; // Circular!
```

**The Fix:** Extract shared types to `src/types/` and keep transformation logic separate from API calls.