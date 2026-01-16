import { useQuery } from '@tanstack/react-query';
import { 
  getTrendingBooks, 
  getPopularBooks, 
  getNewReleases, 
  searchBooks,
  getBookDetails,
  getBookPrompts,
  transformHardcoverBook,
  type HardcoverBook 
} from '@/lib/hardcover';
import { readarrApi } from '@/lib/api';
import type { Book } from '@/types/book';

function transformBooks(books: HardcoverBook[]): Book[] {
  return books.map(transformHardcoverBook);
}

async function enrichAvailability(books: Book[]): Promise<Book[]> {
  const ids = Array.from(
    new Set(
      books
        .map((book) => book.hardcoverId ?? Number(book.id))
        .filter((id) => Number.isFinite(id))
        .map((id) => Number(id))
    )
  );

  if (ids.length === 0) {
    return books;
  }

  try {
    const availability = await readarrApi.getAvailabilityBatch(ids);
    const availabilityMap = new Map(
      availability.results.map((item) => [item.hardcover_id, item])
    );
    return books.map((book) => {
      const hardcoverId = book.hardcoverId ?? Number(book.id);
      const match = Number.isFinite(hardcoverId)
        ? availabilityMap.get(Number(hardcoverId))
        : undefined;
      if (!match) {
        return book;
      }
      return {
        ...book,
        ebookAvailable: match.ebook,
        audiobookAvailable: match.audiobook,
      };
    });
  } catch {
    return books;
  }
}

export function useTrendingBooks(limit: number = 12) {
  return useQuery({
    queryKey: ['hardcover', 'trending', limit],
    queryFn: async () => {
      const data = await getTrendingBooks(limit);
      const books = transformBooks(data.books || []);
      return enrichAvailability(books);
    },
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  });
}

export function usePopularBooks(limit: number = 12) {
  return useQuery({
    queryKey: ['hardcover', 'popular', limit],
    queryFn: async () => {
      const data = await getPopularBooks(limit);
      const books = transformBooks(data.books || []);
      return enrichAvailability(books);
    },
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  });
}

export function useNewReleases(limit: number = 12) {
  return useQuery({
    queryKey: ['hardcover', 'new-releases', limit],
    queryFn: async () => {
      const data = await getNewReleases(limit);
      const books = transformBooks(data.books || []);
      return enrichAvailability(books);
    },
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  });
}

export function useBookSearch(query: string, limit: number = 20) {
  return useQuery({
    queryKey: ['hardcover', 'search', query, limit],
    queryFn: async () => {
      const data = await searchBooks(query, limit);
      return transformBooks(data.books || []);
    },
    enabled: query.length > 0,
    staleTime: 2 * 60 * 1000,
  });
}

export function useBookDetails(bookId: string | undefined) {
  return useQuery({
    queryKey: ['hardcover', 'book', bookId],
    queryFn: async () => {
      if (!bookId) throw new Error('Book ID required');
      const data = await getBookDetails(Number(bookId));
      if (!data.books_by_pk) throw new Error('Book not found');
      return transformHardcoverBook(data.books_by_pk);
    },
    enabled: !!bookId,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

export function useBookPrompts(
  bookId: number | undefined,
  promptLimit: number = 6,
  booksLimit: number = 30
) {
  return useQuery({
    queryKey: ['hardcover', 'book-prompts', bookId, promptLimit, booksLimit],
    queryFn: async () => {
      if (!bookId) throw new Error('Book ID required');
      const data = await getBookPrompts(bookId, promptLimit, booksLimit);
      return data.prompt_summaries || [];
    },
    enabled: Number.isFinite(bookId),
    staleTime: Infinity,
    gcTime: 24 * 60 * 60 * 1000,
  });
}
