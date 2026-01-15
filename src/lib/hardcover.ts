export interface HardcoverBook {
  id: number;
  title: string;
  slug: string;
  release_year: number;
  release_date?: string;
  pages: number;
  description: string;
  cached_image: {
    id: number;
    url: string;
    color?: string;
    width?: number;
    height?: number;
  } | null;
  cached_contributors: Array<{ author: { name: string } }>;
  rating: number;
  ratings_count: number;
  users_count: number;
  book_series?: Array<{
    series_id?: number;
    position: number;
    series: { id: number; name: string; primary_books_count?: number | null };
  }>;
  contributions?: Array<{
    author: { id: number; name: string; slug: string };
  }>;
  taggings?: Array<{ tag: { tag: string } }>;
  editions?: Array<{
    id: number;
    title: string;
    format: string;
    pages: number;
    isbn_10?: string;
    isbn_13?: string;
    asin?: string;
  }>;
}

export interface HardcoverSeries {
  id: number;
  name: string;
  author?: { name: string } | null;
  books_count: number;
  book_series: Array<{
    position: number;
    book: HardcoverBook;
  }>;
}

interface HardcoverResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

import { hardcoverApi } from '@/lib/api';

export async function searchBooks(query: string, limit: number = 20) {
  return hardcoverApi.search(query, limit);
}

export async function getBookDetails(bookId: number, options?: { bypassCache?: boolean }) {
  return hardcoverApi.getDetails(bookId, options);
}

export async function getTrendingBooks(limit: number = 20) {
  return hardcoverApi.getTrending(limit);
}

export async function getPopularBooks(limit: number = 20) {
  return hardcoverApi.getPopular(limit);
}

export async function getNewReleases(limit: number = 20) {
  return hardcoverApi.getNewReleases(limit);
}

export async function getSeriesBooks(seriesId: number, options?: { bypassCache?: boolean }) {
  return hardcoverApi.getSeries(seriesId, options);
}

export async function rebuildSeries(seriesId: number) {
  return hardcoverApi.rebuildSeries(seriesId);
}

export async function getSimilarBooks(bookId: number, limit: number = 10) {
  return hardcoverApi.getSimilar(bookId, limit);
}

export async function getBookPrompts(
  bookId: number,
  promptLimit: number = 6,
  booksLimit: number = 30
) {
  return hardcoverApi.getBookPrompts(bookId, promptLimit, booksLimit);
}

export async function getBooksByAuthor(bookId: number, limit: number = 10) {
  return hardcoverApi.getByAuthor(bookId, limit);
}

export async function getPopularSeries(limit: number = 20, minTotalRatings: number = 500) {
  return hardcoverApi.getPopularSeries(limit, minTotalRatings);
}

// Helper to transform Hardcover book to our app's Book format
export function transformHardcoverBook(hcBook: HardcoverBook) {
  const authors = hcBook.contributions?.map(c => c.author.name) || 
    hcBook.cached_contributors?.map((c: any) => c.author?.name || c.name).filter(Boolean) || 
    [];
  
  const series = hcBook.book_series?.[0];
  const genres = hcBook.taggings?.map(t => t.tag.tag) || [];

  // Extract cover URL from cached_image object
  const coverUrl = typeof hcBook.cached_image === 'object' && hcBook.cached_image?.url 
    ? hcBook.cached_image.url 
    : "/placeholder.svg";

  // Get ISBN from first edition that has one
  const edition = hcBook.editions?.find(e => e.isbn_13 || e.isbn_10);
  const isbn = edition?.isbn_13 || edition?.isbn_10;

  return {
    id: String(hcBook.id),
    title: hcBook.title,
    author: authors.join(", ") || "Unknown Author",
    cover: coverUrl,
    description: hcBook.description || "",
    publishedDate: hcBook.release_date || String(hcBook.release_year || ""),
    genres,
    rating: hcBook.rating || 0,
    series: series?.series.name,
    seriesPosition: series?.position,
    seriesId: series?.series_id ?? series?.series?.id,
    isbn,
    pageCount: hcBook.pages,
    hardcoverId: hcBook.id,
    hardcoverSlug: hcBook.slug,
    defaultEditionId: (hcBook as any).default_edition_id,
    usersCount: hcBook.users_count,
    activitiesCount: (hcBook as any).activities_count,
    ebookAvailable: (hcBook as any).ebook_available || false,
    audiobookAvailable: (hcBook as any).audiobook_available || false,
  };
}

export function normalizeSeriesBooks(
  bookSeries: Array<{ position?: number | null; book?: HardcoverBook }> = [],
  seriesContext?: { id: number; name: string }
) {
  const booksByPosition = new Map<number, ReturnType<typeof transformHardcoverBook> & { position?: number }>();
  const unpositioned: Array<ReturnType<typeof transformHardcoverBook> & { position?: number }> = [];

  for (const entry of bookSeries) {
    if (!entry?.book) continue;
    const transformed = {
      ...transformHardcoverBook(entry.book),
      position: entry.position ?? entry.book.book_series?.[0]?.position ?? undefined,
    };
    if (seriesContext) {
      (transformed as any).seriesId = seriesContext.id;
      transformed.series = seriesContext.name;
    }
    if (transformed.position == null) {
      unpositioned.push(transformed);
      continue;
    }
    const existing = booksByPosition.get(transformed.position);
    if (!existing) {
      booksByPosition.set(transformed.position, transformed);
      continue;
    }
    const existingPopularity = existing.activitiesCount ?? 0;
    const currentPopularity = transformed.activitiesCount ?? 0;
    if (currentPopularity > existingPopularity) {
      booksByPosition.set(transformed.position, transformed);
    }
  }

  const positioned = Array.from(booksByPosition.entries())
    .sort(([posA], [posB]) => posA - posB)
    .map(([, book]) => book);

  const tail = unpositioned.sort((a, b) => (b.activitiesCount ?? 0) - (a.activitiesCount ?? 0));

  return [...positioned, ...tail];
}
