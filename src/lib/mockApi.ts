// Mock API layer for frontend development without backend
import { mockBooks, mockRequests } from '@/data/mockBooks';
import { ApiUser } from './api';

// Check if backend is available
let backendAvailable: boolean | null = null;

export async function checkBackendAvailable(): Promise<boolean> {
  if (backendAvailable !== null) return backendAvailable;
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
    
    const response = await fetch('/api/users/check/admin-exists', {
      method: 'GET',
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    // Must be a successful response with JSON content
    if (!response.ok) {
      backendAvailable = false;
      return false;
    }
    
    // Check if response is actually JSON (not HTML from SPA fallback)
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      backendAvailable = false;
      return false;
    }
    
    // Try to parse JSON to confirm it's a real API response
    const data = await response.json();
    backendAvailable = typeof data.admin_exists === 'boolean';
    return backendAvailable;
  } catch {
    backendAvailable = false;
    return false;
  }
}

// Reset backend check (useful for retrying)
export function resetBackendCheck() {
  backendAvailable = null;
}

export function isBackendAvailable(): boolean | null {
  return backendAvailable;
}

// Mock user for development
export const MOCK_USER: ApiUser = {
  id: 1,
  email: 'admin@bookeerr.local',
  username: 'admin',
  full_name: 'Admin User',
  is_active: true,
  is_admin: true,
  can_request_ebook: true,
  can_request_audiobook: true,
  auto_approve_ebooks: false,
  auto_approve_audiobooks: false,
  created_at: new Date().toISOString(),
};

// Transform mock books to match API format
function transformMockBookToApi(book: typeof mockBooks[0], index: number) {
  return {
    id: 1000 + index,
    hardcover_id: 1000 + index,
    title: book.title,
    author_name: book.author,
    cover_url: book.cover,
    description: book.description,
    release_date: book.publishedDate,
    genres: book.genres,
    rating: book.rating,
    series_name: book.series || null,
    series_position: book.seriesPosition || null,
    page_count: book.pageCount,
    cached_data: {
      contributions: [{ author: { name: book.author, id: index + 1 } }],
      image: { url: book.cover },
      description: book.description,
      release_date: book.publishedDate,
      pages: book.pageCount,
      rating: book.rating,
    },
  };
}

// Mock API responses
export const mockApiResponses = {
  // Users API
  'GET /api/users/check/admin-exists': () => ({ admin_exists: true }),
  'GET /api/users/me': () => MOCK_USER,
  'GET /api/users/': () => [MOCK_USER],
  'POST /api/auth/login': () => ({ user_id: 1, is_admin: true }),
  
  // Hardcover API
  'GET /api/hardcover/trending': () => ({
    books: mockBooks.slice(0, 6).map(transformMockBookToApi),
  }),
  'GET /api/hardcover/popular': () => ({
    books: [...mockBooks].sort((a, b) => b.rating - a.rating).slice(0, 6).map(transformMockBookToApi),
  }),
  'GET /api/hardcover/new-releases': () => ({
    books: [...mockBooks]
      .sort((a, b) => new Date(b.publishedDate).getTime() - new Date(a.publishedDate).getTime())
      .slice(0, 6)
      .map(transformMockBookToApi),
  }),
  'GET /api/hardcover/popular-series': () => ({
    series: [
      { id: 1, name: 'The Enchanted Realms', book_count: 3, total_ratings: 15000, author_name: 'Elena Darkwood' },
      { id: 2, name: 'Coastal Hearts', book_count: 2, total_ratings: 8000, author_name: 'Sarah Mitchell' },
      { id: 3, name: 'The Crusader Saga', book_count: 4, total_ratings: 20000, author_name: 'Robert Stonebridge' },
    ],
  }),
  'GET /api/hardcover/search': (query: string) => ({
    books: mockBooks
      .filter(b => b.title.toLowerCase().includes(query.toLowerCase()) || 
                   b.author.toLowerCase().includes(query.toLowerCase()))
      .map(transformMockBookToApi),
  }),
  'GET /api/hardcover/search-grouped': (query: string) => {
    const filtered = mockBooks.filter(b => 
      b.title.toLowerCase().includes(query.toLowerCase()) || 
      b.author.toLowerCase().includes(query.toLowerCase())
    );
    return {
      books: filtered.map(transformMockBookToApi),
      series: [],
      authors: [...new Set(filtered.map(b => b.author))].map((name, i) => ({ id: i + 1, name })),
    };
  },
  'GET /api/hardcover/author': (name: string) => {
    const normalized = name || 'Unknown Author';
    const filtered = mockBooks.filter((book) =>
      book.author.toLowerCase().includes(normalized.toLowerCase())
    );
    const books = filtered.length ? filtered : mockBooks.slice(0, 6);
    const seriesMap = new Map<string, number>();
    books.forEach((book) => {
      if (!book.series) return;
      seriesMap.set(book.series, (seriesMap.get(book.series) || 0) + 1);
    });
    const series = Array.from(seriesMap.entries()).map(([seriesName, count], index) => ({
      id: index + 1,
      name: seriesName,
      books_count: count,
    }));
    const cover = books[0]?.cover;

    return {
      author: {
        id: 1,
        name: normalized,
        slug: normalized.toLowerCase().replace(/\s+/g, '-'),
        bio: `${normalized} is a featured author in the Bookkeep catalog.`,
        image_url: cover,
      },
      books: books.map(transformMockBookToApi),
      books_total: books.length,
      series,
      series_total: series.length,
    };
  },
  
  // Books API
  'GET /api/books/': () => mockBooks.map(transformMockBookToApi),
  
  // Requests API
  'GET /api/requests/': () => mockRequests.map((req, i) => ({
    id: i + 1,
    book_id: parseInt(req.bookId),
    user_id: 1,
    format: req.format,
    status: req.status,
    notes: req.notes,
    created_at: req.createdAt,
    updated_at: req.updatedAt,
    book: transformMockBookToApi(mockBooks[parseInt(req.bookId) - 1] || mockBooks[0], parseInt(req.bookId) - 1),
    user: MOCK_USER,
  })),
  
  // Readarr API
  'GET /api/readarr/': () => [],
  'GET /api/readarr/configured-formats': () => ({ ebook: false, audiobook: false }),
  
  // Booklore API
  'GET /api/booklore/': () => [],
  
  // Jobs API
  'GET /api/jobs/': () => [
    { name: 'sync_readarr', type: 'sync', interval_seconds: 3600, last_execution: null, next_execution: null, is_enabled: true },
    { name: 'refresh_availability', type: 'refresh', interval_seconds: 86400, last_execution: null, next_execution: null, is_enabled: true },
  ],
  'GET /api/jobs/intervals': () => [
    { value: 3600, label: '1 hour' },
    { value: 21600, label: '6 hours' },
    { value: 43200, label: '12 hours' },
    { value: 86400, label: '24 hours' },
  ],
  
  // Settings API
  'GET /api/settings/hardcover-token': () => ({ 
    hardcover_api_token: null, 
    hardcover_api_token_source: 'none',
    has_hardcover_token: false 
  }),
};

// Get mock response for an endpoint
export function getMockResponse(method: string, path: string): any {
  // Normalize path (remove query params for matching)
  const basePath = path.split('?')[0];
  const queryString = path.split('?')[1] || '';
  const params = new URLSearchParams(queryString);
  
  const key = `${method} ${basePath}`;
  
  // Direct match
  if (mockApiResponses[key as keyof typeof mockApiResponses]) {
    const handler = mockApiResponses[key as keyof typeof mockApiResponses];
    if (typeof handler === 'function') {
      // Pass query param for search/author endpoints
      if (basePath.includes('search')) {
        return handler(params.get('query') || '');
      }
      if (basePath.includes('/api/hardcover/author')) {
        return handler(params.get('name') || '');
      }
      return handler('');
    }
    return handler;
  }
  
  // Pattern matching for dynamic routes
  if (basePath.startsWith('/api/hardcover/details/')) {
    const bookId = parseInt(basePath.split('/').pop() || '0');
    const book = mockBooks[bookId % mockBooks.length];
    return {
      books_by_pk: {
        id: bookId,
        title: book?.title || 'Unknown Book',
        contributions: [{ author: { name: book?.author || 'Unknown', id: 1 } }],
        image: { url: book?.cover },
        description: book?.description,
        release_date: book?.publishedDate,
        pages: book?.pageCount,
        users_read_count: 1000,
        ratings_count: 500,
        rating: book?.rating,
        book_series: book?.series ? [{
          series: { id: 1, name: book.series },
          position: book.seriesPosition,
        }] : [],
        taggings: (book?.genres || []).map((g, i) => ({ tag: { tag: g, id: i } })),
        editions: [],
      },
    };
  }
  
  if (basePath.startsWith('/api/hardcover/series/')) {
    return {
      series_by_pk: {
        id: 1,
        name: 'The Enchanted Realms',
        books_count: 3,
        books: mockBooks.filter(b => b.series === 'The Enchanted Realms').map(transformMockBookToApi),
      },
    };
  }
  
  if (basePath.startsWith('/api/requests/by-hardcover/')) {
    return { ebook: null, audiobook: null, book_id: null };
  }
  
  if (basePath.startsWith('/api/readarr/availability/')) {
    return { ebook: false, audiobook: false };
  }
  
  // Default: return empty/null response
  console.warn(`[MockAPI] No mock for: ${method} ${path}`);
  return null;
}
