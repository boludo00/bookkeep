# TypeScript Types Reference

## Contents
- Domain Types Organization
- Interface Patterns
- API Response Types
- Component Prop Types
- Utility Types Usage

## Domain Types Organization

All domain types live in `src/types/book.ts`. Import with type-only syntax:

```typescript
import type { Book, BookRequest, RequestStatus } from '@/types/book';
```

## Interface Patterns

### Core Entity Interface

```typescript
// src/types/book.ts
export interface Book {
  id: string;
  title: string;
  author: string;
  cover: string;
  description: string;
  publishedDate: string;
  genres: string[];
  rating: number;
  // Optional external system fields
  series?: string;
  seriesPosition?: number;
  seriesId?: number;
  isbn?: string;
  pageCount?: number;
  hardcoverId?: number;
  hardcoverSlug?: string;
  // Availability flags
  ebookAvailable?: boolean;
  audiobookAvailable?: boolean;
}
```

### Request Entity with Status Union

```typescript
export interface BookRequest {
  id: string;
  bookId: string;
  book: Book;
  userId: string;
  userName: string;
  format: 'ebook' | 'audiobook';
  status: 'pending' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found';
  source?: 'user_request' | 'booklore_import';
  notes?: string;
  adminNotes?: string;
  createdAt: string;
  updatedAt: string;
}
```

### Batch Response Pattern

```typescript
// For endpoints returning arrays with metadata
export interface RequestStatus {
  hardcover_id: number;
  book_id: number | null;
  ebook: 'pending' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found' | null;
  audiobook: 'pending' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found' | null;
}

export interface RequestStatusBatchResponse {
  results: RequestStatus[];
}
```

## API Response Types

### Inline Response Types

```typescript
// src/lib/api.ts
export const requestsApi = {
  getByHardcoverId: (hardcoverId: number) =>
    apiRequest<{
      ebook: string | null;
      audiobook: string | null;
      ebook_readarr_book_id: number | null;
      audiobook_readarr_book_id: number | null;
      book_id: number | null;
    }>(`/api/requests/by-hardcover/${hardcoverId}`),
};
```

### Complex Nested Response

```typescript
export const hardcoverApi = {
  getEditions: (bookId: number, format?: 'ebook' | 'audiobook') =>
    apiRequest<{
      default_cover_edition_id: number | null;
      default_ebook_edition_id: number | null;
      default_audio_edition_id: number | null;
      editions: Array<{
        id: number;
        title?: string;
        score?: number;
        reading_format_id?: number;
        reading_format?: string;
        language?: string;
        pages?: number;
        audio_seconds?: number;
      }>;
    }>(`/api/hardcover/editions/${bookId}`),
};
```

### User API Types

```typescript
// src/lib/api.ts
export interface ApiUser {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  is_admin: boolean;
  can_request_ebook: boolean;
  can_request_audiobook: boolean;
  can_download: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}
```

## Component Prop Types

### Standard Props Interface

```typescript
// src/components/books/BookCard.tsx
interface BookCardProps {
  book: Book;
  status?: 'available' | 'pending' | 'none';
  showRating?: boolean;
  enableRequestStatus?: boolean;
  showRequestButton?: boolean;
  requestStatus?: { ebook?: string | null; audiobook?: string | null };
}
```

### Hook Options Interface

```typescript
// src/hooks/useAvailabilityPolling.ts
interface PendingRequest {
  hardcoverId: number;
  format: 'ebook' | 'audiobook';
  readarrBookId: number | null;
}

interface AvailabilityPollingOptions {
  pendingRequests: PendingRequest[];
  enabled?: boolean;
  seriesId?: string | number;
}
```

### Context Type Pattern

```typescript
// src/contexts/UserContext.tsx
interface UserContextType {
  user: ApiUser | null;
  isLoading: boolean;
  isAdmin: boolean;
  isLoggedIn: boolean;
  refetchUser: () => void;
  logout: () => void;
}
```

## Utility Types Usage

### Record for Config Objects

```typescript
const statusConfig: Record<string, { 
  label: string; 
  variant: 'default' | 'secondary' | 'outline';
  icon?: typeof CheckCircle;
}> = {
  pending: { label: 'Pending', variant: 'secondary', icon: Clock },
  approved: { label: 'Approved', variant: 'default', icon: CheckCircle },
};
```

### Partial for Optional Updates

```typescript
// When updating only some fields
function updateBook(id: number, updates: Partial<Book>) {
  return apiRequest<Book>(`/api/books/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}
```

### WARNING: Excessive `any` Types

**The Problem:**

```typescript
// BAD - Loses all type safety
export const booksApi = {
  getAll: () => apiRequest<Array<any>>('/api/books/'),
  create: (book: any) => apiRequest<any>('/api/books/', { /* ... */ }),
};
```

**The Fix:** Define response interfaces. Even a partial interface is better than `any`:

```typescript
interface BookResponse {
  id: number;
  title: string;
  hardcover_id?: number;
  // Add fields as you discover them
}