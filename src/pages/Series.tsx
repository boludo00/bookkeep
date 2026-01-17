import { useEffect, useMemo } from 'react';
import { BookOpen, CheckCircle, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query';
import { booksApi, readarrApi, requestsApi } from '@/lib/api';
import { getPopularSeries, getSeriesBooks, normalizeSeriesBooks, transformHardcoverBook } from '@/lib/hardcover';
import { Skeleton } from '@/components/ui/skeleton';
import { useAvailabilityPolling } from '@/hooks/useAvailabilityPolling';
import type { Book } from '@/types/book';

const SERIES_PAGE_SIZE = 24;

interface SeriesItem {
  id: number;
  name: string;
  books_count: number;
  owned_count?: number;
  first_book: any;
}

export default function Series() {
  const {
    data: seriesData,
    isLoading: seriesLoading,
    fetchNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['popular-series', SERIES_PAGE_SIZE],
    queryFn: ({ pageParam = 0 }) => getPopularSeries(SERIES_PAGE_SIZE, 500, pageParam),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage?.series?.length === SERIES_PAGE_SIZE
        ? allPages.length * SERIES_PAGE_SIZE
        : undefined,
    staleTime: 5 * 60 * 1000,
  });

  const { data: booksData = [], isLoading: booksLoading } = useQuery({
    queryKey: ['books', 'all'],
    queryFn: () => booksApi.getAll(0, 2000),
  });

  const seriesList: SeriesItem[] = useMemo(
    () => seriesData?.pages.flatMap((page) => page.series) ?? [],
    [seriesData]
  );
  const lastPageSize = seriesData?.pages?.[seriesData.pages.length - 1]?.series?.length ?? 0;
  const canLoadMore = lastPageSize === SERIES_PAGE_SIZE;
  const books: Book[] = useMemo(
    () =>
      booksData.map((book: any) => ({
        id: String(book.id),
        title: book.title,
        author: book.author,
        cover: book.cover_url || '/placeholder.svg',
        description: book.description || '',
        publishedDate: book.published_date || '',
        genres: book.genres ? (typeof book.genres === 'string' ? book.genres.split(',') : book.genres) : [],
        rating: book.rating || 0,
        series: book.series,
        seriesPosition: book.series_position,
        seriesId: book.series_id,
        isbn: book.isbn,
        pageCount: book.page_count,
        hardcoverId: book.hardcover_id,
        hardcoverSlug: book.hardcover_slug,
        ebookAvailable: book.ebook_available || false,
        audiobookAvailable: book.audiobook_available || false,
      })),
    [booksData]
  );

  const seriesQueries = useQueries({
    queries: seriesList.map((series) => ({
      queryKey: ['series', series.id],
      queryFn: () => getSeriesBooks(series.id),
      enabled: Number.isFinite(series.id),
    })),
  });

  const seriesBooksById = useMemo(() => {
    return seriesList.map((series, index) => {
      const seriesDetail = seriesQueries[index]?.data?.series_by_pk;
      const seriesContext = {
        id: seriesDetail?.id ?? series.id,
        name: seriesDetail?.name ?? series.name,
      };
      const seriesBooks = seriesDetail?.book_series
        ? normalizeSeriesBooks(seriesDetail.book_series, seriesContext)
        : [];
      return { series, seriesDetail, seriesBooks };
    });
  }, [seriesList, seriesQueries]);

  const ownedCountBySeriesId = useMemo(() => {
    const map: Record<number, number> = {};
    books.forEach((book) => {
      if (!book.seriesId) {
        return;
      }
      const isOwned = book.ebookAvailable || book.audiobookAvailable;
      if (!isOwned) {
        return;
      }
      map[book.seriesId] = (map[book.seriesId] ?? 0) + 1;
    });
    return map;
  }, [books]);

  const availabilityIds = useMemo(() => {
    const ids = new Set<number>();
    seriesBooksById.forEach(({ seriesBooks }) => {
      seriesBooks.forEach((book) => {
        const hardcoverId = book.hardcoverId ?? Number(book.id);
        if (Number.isFinite(hardcoverId)) {
          ids.add(Number(hardcoverId));
        }
      });
    });
    return Array.from(ids);
  }, [seriesBooksById]);

  const isbnMap = useMemo(() => {
    const map: Record<number, string[]> = {};
    seriesBooksById.forEach(({ seriesBooks }) => {
      seriesBooks.forEach((book) => {
        const hardcoverId = book.hardcoverId ?? Number(book.id);
        if (!Number.isFinite(hardcoverId) || !book.isbn) {
          return;
        }
        map[Number(hardcoverId)] = [book.isbn];
      });
    });
    return map;
  }, [seriesBooksById]);

  const { data: availabilityBatch } = useQuery({
    queryKey: ['readarr', 'availability', 'series-list', availabilityIds],
    queryFn: () => readarrApi.getAvailabilityBatch(availabilityIds, isbnMap),
    enabled: availabilityIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const availabilityMap = useMemo(() => {
    return new Map(
      availabilityBatch?.results.map((item) => [item.hardcover_id, item]) ?? []
    );
  }, [availabilityBatch]);

  // Fetch request statuses for all books in all series
  const { data: requestStatusBatch } = useQuery({
    queryKey: ['requests', 'by-hardcover', 'series-list', availabilityIds],
    queryFn: () => requestsApi.getByHardcoverBatch(availabilityIds),
    enabled: availabilityIds.length > 0,
    staleTime: 0, // Always refetch after mutations to show updated request status
  });

  const requestStatusMap = useMemo(() => {
    return new Map(
      requestStatusBatch?.results.map((item: any) => [item.hardcover_id, item]) ?? []
    );
  }, [requestStatusBatch]);

  // Find books with pending requests that need polling
  const pendingRequests = useMemo(() => {
    if (!requestStatusBatch?.results) return [];

    return requestStatusBatch.results
      .filter((status: any) => status.ebook === 'processing' || status.audiobook === 'processing')
      .flatMap((status: any) => {
        const requests: Array<{ hardcoverId: number; format: 'ebook' | 'audiobook'; readarrBookId: number | null }> = [];
        if (status.ebook === 'processing') {
          requests.push({
            hardcoverId: status.hardcover_id,
            format: 'ebook' as const,
            readarrBookId: status.ebook_readarr_book_id || null,
          });
        }
        if (status.audiobook === 'processing') {
          requests.push({
            hardcoverId: status.hardcover_id,
            format: 'audiobook' as const,
            readarrBookId: status.audiobook_readarr_book_id || null,
          });
        }
        return requests;
      });
  }, [requestStatusBatch]);

  // Poll for availability updates on books with pending requests
  useAvailabilityPolling({
    pendingRequests,
    enabled: pendingRequests.length > 0,
  });

  const isLoading = seriesLoading || booksLoading;

  useEffect(() => {
    if (!canLoadMore) {
      return;
    }

    const maybeFetch = () => {
      if (isFetchingNextPage || !canLoadMore) {
        return;
      }
      const scrollingElement = document.scrollingElement || document.documentElement;
      const scrollBottom =
        scrollingElement.scrollTop + window.innerHeight;
      const threshold = scrollingElement.scrollHeight - 400;
      if (scrollBottom >= threshold) {
        fetchNextPage();
      }
    };

    window.addEventListener('scroll', maybeFetch, { passive: true });
    window.addEventListener('resize', maybeFetch);
    const intervalId = window.setInterval(maybeFetch, 800);
    maybeFetch();

    return () => {
      window.removeEventListener('scroll', maybeFetch);
      window.removeEventListener('resize', maybeFetch);
      window.clearInterval(intervalId);
    };
  }, [fetchNextPage, canLoadMore, isFetchingNextPage, seriesList.length]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Series</h1>
        <p className="text-muted-foreground mt-1">
          Browse book series and collections
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 9 }).map((_, i) => (
            <div
              key={i}
              className="relative rounded-xl overflow-hidden bg-card border border-border"
            >
              {/* Background skeleton */}
              <div className="absolute inset-0 bg-muted/30" />
              
              {/* Content skeleton */}
              <div className="relative p-6">
                <div className="flex gap-4">
                  {/* Cover skeleton */}
                  <Skeleton className="flex-shrink-0 w-20 h-28 rounded" />
                  
                  {/* Info skeleton */}
                  <div className="flex-1 min-w-0 pt-2 space-y-2">
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-4 w-1/3 mt-2" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : seriesList.length === 0 ? (
        <div className="text-center py-12">
          <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium text-foreground">No series found</h3>
          <p className="text-muted-foreground mt-1">
            Series will appear here as books are added
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {seriesBooksById.map(({ series, seriesDetail, seriesBooks }) => {
              const isWholePosition = (position?: number | null) =>
                typeof position === 'number' &&
                Number.isFinite(position) &&
                Math.floor(position) === position;
              const originalBooks = seriesBooks.filter((book) =>
                isWholePosition((book as any).position ?? book.seriesPosition)
              );
              const fallbackBook = series.first_book ? transformHardcoverBook(series.first_book) : null;
              const cover = seriesBooks[0]?.cover || fallbackBook?.cover || '/placeholder.svg';
            const author =
              seriesDetail?.author?.name ||
              seriesBooks[0]?.author ||
              fallbackBook?.author ||
              'Unknown Author';
            // Check if a book is actually available (has files)
            const isAvailable = (book: Book) => {
              const hardcoverId = book.hardcoverId ?? Number(book.id);
              const match = Number.isFinite(hardcoverId)
                ? availabilityMap.get(Number(hardcoverId))
                : undefined;
              const ebookAvailable = book.ebookAvailable || match?.ebook;
              const audiobookAvailable = book.audiobookAvailable || match?.audiobook;
              return ebookAvailable || audiobookAvailable;
            };

            // Check if a book is requested (but not available)
            const isRequested = (book: Book) => {
              const hardcoverId = book.hardcoverId ?? Number(book.id);
              if (!Number.isFinite(hardcoverId)) return false;

              const requestStatus = requestStatusMap.get(Number(hardcoverId));
              if (!requestStatus) return false;

              const hasRequest = (requestStatus as any).ebook || (requestStatus as any).audiobook;
              return hasRequest && !isAvailable(book);
            };

            const expandedAvailableCount = seriesBooks.filter(isAvailable).length;
            const originalAvailableCount = originalBooks.filter(isAvailable).length;
            const expandedRequestedCount = seriesBooks.filter(isRequested).length;
            const originalRequestedCount = originalBooks.filter(isRequested).length;
            const expandedCount = seriesBooks.length;
            const originalCount = originalBooks.length;
            const availableCount =
              expandedCount > 0
                ? expandedAvailableCount
                : series.owned_count != null
                  ? series.owned_count
                  : (ownedCountBySeriesId[series.id] ?? 0);
            const requestedCount =
              expandedCount > 0
                ? expandedRequestedCount
                : 0;
            const totalCount =
              originalBooks.length > 0
                ? originalBooks.length
                : (seriesDetail?.books_count || series.books_count || seriesBooks.length);

              return (
                <Link
                  key={series.id}
                  to={`/series/${series.id}`}
                  className="group relative rounded-xl overflow-hidden bg-card border border-border card-hover"
                >
                  {/* Background */}
                  <div className="absolute inset-0">
                    <img
                      src={cover}
                      alt=""
                      className="h-full w-full object-cover opacity-30 blur-xl scale-110"
                    />
                    <div className="absolute inset-0 bg-card/80" />
                  </div>

                  {/* Content */}
                  <div className="relative p-6">
                    <div className="flex gap-4">
                      {/* Cover */}
                      <div className="flex-shrink-0 w-20 h-28">
                        {(seriesBooks[0] || fallbackBook) && (
                          <img
                            src={cover}
                            alt={seriesBooks[0]?.title || fallbackBook?.title || series.name}
                            className="w-full h-full object-cover rounded shadow-lg"
                          />
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0 pt-2">
                        <h3 className="font-semibold text-foreground text-lg line-clamp-2">
                          {seriesDetail?.name || series.name}
                        </h3>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                          {author}
                        </p>
                        {/* Status indicators */}
                        {availableCount > 0 || requestedCount > 0 ? (
                          <div className="flex items-center gap-2 mt-2 flex-wrap">
                            {/* Available count */}
                            {availableCount > 0 && (
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/20 border border-emerald-500/30">
                                <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
                                <span className="text-xs font-medium text-emerald-400">
                                  {originalCount > 0 ? `${originalAvailableCount}/${originalCount} available` : `${availableCount}/${totalCount} available`}
                                </span>
                              </div>
                            )}

                            {/* Requested count */}
                            {requestedCount > 0 && (
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-blue-500/20 border border-blue-500/30">
                                <Clock className="h-3.5 w-3.5 text-blue-400" />
                                <span className="text-xs font-medium text-blue-400">
                                  {originalCount > 0 ? `${originalRequestedCount} requested` : `${requestedCount} requested`}
                                </span>
                              </div>
                            )}

                            {/* Expanded counts if different from original */}
                            {expandedCount > 0 && expandedCount !== originalCount && (
                              <>
                                {expandedAvailableCount > 0 && (
                                  <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                                    <span className="text-xs font-medium text-emerald-300">
                                      {expandedAvailableCount}/{expandedCount} expanded
                                    </span>
                                  </div>
                                )}
                              </>
                            )}

                            {/* Complete indicator */}
                            {totalCount > 0 && availableCount === totalCount && expandedCount === originalCount && (
                              <span className="text-xs text-emerald-400 font-medium">Complete!</span>
                            )}
                          </div>
                        ) : (
                          <p className="text-sm text-primary mt-2">
                            {totalCount} book{totalCount !== 1 ? 's' : ''}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>

          {canLoadMore && <div className="h-6" />}

          {isFetchingNextPage && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="relative rounded-xl overflow-hidden bg-card border border-border"
                >
                  <div className="absolute inset-0 bg-muted/30" />
                  <div className="relative p-6">
                    <div className="flex gap-4">
                      <Skeleton className="flex-shrink-0 w-20 h-28 rounded" />
                      <div className="flex-1 min-w-0 pt-2 space-y-2">
                        <Skeleton className="h-5 w-3/4" />
                        <Skeleton className="h-4 w-1/2" />
                        <Skeleton className="h-4 w-1/3 mt-2" />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
