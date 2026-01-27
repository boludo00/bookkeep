import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, RefreshCw, Clock } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSeriesBooks, normalizeSeriesBooks, rebuildSeries } from '@/lib/hardcover';
import { requestsApi, readarrApi } from '@/lib/api';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { BookCard } from '@/components/books/BookCard';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';
import { useAvailabilityPolling } from '@/hooks/useAvailabilityPolling';
import type { Book, RequestStatusBatchResponse, AvailabilityBatchResponse, RequestStatus, AvailabilityStatus } from '@/types/book';

export default function SeriesDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [seriesView, setSeriesView] = useState<'original' | 'expanded'>('original');
  const { isAdmin } = useUser();
  
  const { data: seriesData, isLoading, error } = useQuery({
    queryKey: ['series', id],
    queryFn: () => getSeriesBooks(Number(id)),
    enabled: !!id && !isNaN(Number(id)),
    staleTime: 7 * 24 * 60 * 60 * 1000,
  });

  const series = seriesData?.series_by_pk;
  
  const allBooks: Book[] = series?.book_series
    ? normalizeSeriesBooks(series.book_series, { id: series.id, name: series.name })
    : [];
  const isWholePosition = (position?: number | null) =>
    typeof position === 'number' && Number.isFinite(position) && Math.floor(position) === position;
  const originalBooks = allBooks.filter((book) =>
    isWholePosition((book as any).position ?? book.seriesPosition)
  );
  const books = seriesView === 'original' ? originalBooks : allBooks;

  // Get first book's cover for hero background
  const heroCover = books[0]?.cover || allBooks[0]?.cover || '/placeholder.svg';
  
  // Collect unique genres from all books
  const allGenres = books.flatMap(book => book.genres || []);
  const uniqueGenres = [...new Set(allGenres)].slice(0, 5);

  const hardcoverIds = books
    .map((book) => book.hardcoverId ?? Number(book.id))
    .filter((bookId): bookId is number => Number.isFinite(bookId))
    .map((bookId) => Number(bookId));

  const isbnMap = books.reduce<Record<number, string[]>>((acc, book) => {
    const hardcoverId = book.hardcoverId ?? Number(book.id);
    if (!Number.isFinite(hardcoverId) || !book.isbn) {
      return acc;
    }
    acc[Number(hardcoverId)] = [book.isbn];
    return acc;
  }, {});

  const { data: readarrAvailability } = useQuery<AvailabilityBatchResponse>({
    queryKey: ['readarr', 'availability', 'series', id, hardcoverIds],
    queryFn: () => readarrApi.getAvailabilityBatch(hardcoverIds, isbnMap),
    enabled: hardcoverIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const { data: requestStatuses, refetch: refetchRequestStatuses } = useQuery<RequestStatusBatchResponse>({
    queryKey: ['requests', 'by-hardcover', 'series', id, hardcoverIds],
    queryFn: () => requestsApi.getByHardcoverBatch(hardcoverIds),
    enabled: hardcoverIds.length > 0,
    staleTime: 30 * 1000, // Cache for 30 seconds - fresh enough for UI updates
    refetchOnMount: true, // Refetch on mount but use cache if fresh
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
  });

  const availabilityMap = new Map<number, AvailabilityStatus>(
    readarrAvailability?.results.map((item) => [item.hardcover_id, item]) ?? []
  );

  const requestStatusMap = new Map<number, RequestStatus>(
    requestStatuses?.results.map((item) => [item.hardcover_id, item]) ?? []
  );

  // Find books with pending requests that need polling
  const pendingRequests = useMemo(() => {
    if (!requestStatuses?.results) return [];

    return requestStatuses.results
      .filter((status) => status.ebook === 'processing' || status.audiobook === 'processing')
      .flatMap((status) => {
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
  }, [requestStatuses]);

  // Poll for availability updates on books with pending requests
  useAvailabilityPolling({
    pendingRequests,
    enabled: pendingRequests.length > 0,
    seriesId: id,
  });

  const booksWithAvailability = books.map((book) => {
    const hardcoverId = book.hardcoverId ?? Number(book.id);
    const match = Number.isFinite(hardcoverId) ? availabilityMap.get(Number(hardcoverId)) : undefined;
    if (!match) {
      return book;
    }
    return {
      ...book,
      ebookAvailable: book.ebookAvailable || match.ebook,
      audiobookAvailable: book.audiobookAvailable || match.audiobook,
    };
  });

  // Count available books
  const availableCount = booksWithAvailability.filter(
    (b) => b.ebookAvailable || b.audiobookAvailable
  ).length;

  // Count books that are requested (not available, but have active requests)
  const requestedCount = booksWithAvailability.filter((book) => {
    const hardcoverId = book.hardcoverId ?? Number(book.id);
    const isAvailable = book.ebookAvailable || book.audiobookAvailable;

    // If book is available, it's not requested
    if (isAvailable) return false;

    // Check if book has any active requests (any format)
    const requestStatus = Number.isFinite(hardcoverId)
      ? requestStatusMap.get(Number(hardcoverId))
      : undefined;

    if (!requestStatus) return false; // No requests

    // Count as requested if there's an active request for any format (not denied)
    const ebookStatus = requestStatus.ebook;
    const audiobookStatus = requestStatus.audiobook;

    return (ebookStatus && ebookStatus !== 'denied') || (audiobookStatus && audiobookStatus !== 'denied');
  }).length;

  // Rebuild series data (admin only)
  const rebuildSeriesMutation = useMutation({
    mutationFn: () => rebuildSeries(Number(id)),
    onSuccess: (data) => {
      queryClient.setQueryData(['series', id], data);
      queryClient.invalidateQueries({ queryKey: ['popular-series'] });
      toast.success('Series cache cleared and rebuilt.');
    },
    onError: (error: Error) => {
      toast.error('Failed to rebuild series', {
        description: error.message,
      });
    },
  });

  // Show clear button if there are any requested books
  const hasRequests = requestedCount > 0;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-64 w-full rounded-2xl" />
        <div className="flex gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="w-[140px] h-[210px] rounded-lg flex-shrink-0" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !series) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Series Not Found</h1>
        <Link to="/series">
          <Button variant="outline">Back to Series</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Back Button */}
      <Link
        to="/series"
        className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Series
      </Link>

      {/* Hero Section */}
      <div className="relative rounded-2xl overflow-hidden">
        {/* Blurred Background – hidden on mobile for performance */}
        <div className="absolute inset-0 hidden md:block">
          <img
            src={heroCover}
            alt=""
            className="h-full w-full object-cover opacity-30 blur-3xl scale-110"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/80" />
        </div>

        {/* Content */}
        <div className="relative flex flex-col md:flex-row gap-8 p-8">
          {/* Series Cover (First Book) */}
          <div className="flex-shrink-0">
            <img
              src={heroCover}
              alt={series.name}
              loading="lazy"
              className="w-48 md:w-56 rounded-xl shadow-2xl mx-auto md:mx-0"
            />
          </div>

          {/* Series Info */}
          <div className="flex-1 space-y-4">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-foreground">
                {series.name}
              </h1>
              <p className="text-lg text-muted-foreground mt-2">
                {books.length} Book{books.length !== 1 ? 's' : ''}
                {uniqueGenres.length > 0 && (
                  <span> | {uniqueGenres.join(', ')}</span>
                )}
              </p>
            </div>

            <div className="mt-6 flex items-center gap-3">
              <Switch
                checked={seriesView === 'original'}
                onCheckedChange={(checked) => setSeriesView(checked ? 'original' : 'expanded')}
                aria-label="Show Original Series"
              />
              <span className="text-sm text-muted-foreground">Show Original Series</span>
            </div>

            {/* Availability Summary */}
            <div className="flex flex-wrap gap-2">
              {availableCount > 0 && (
                <Badge variant="secondary" className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                  <BookOpen className="h-3 w-3 mr-1" />
                  {availableCount} Available
                </Badge>
              )}
              {requestedCount > 0 && (
                <Badge variant="secondary" className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                  <Clock className="h-3 w-3 mr-1" />
                  {requestedCount} Requested
                </Badge>
              )}
            </div>

            {/* Admin Actions */}
            {isAdmin && (
              <div className="flex flex-wrap gap-3 pt-2">
                <Button
                  size="lg"
                  variant="outline"
                  onClick={() => rebuildSeriesMutation.mutate()}
                  disabled={rebuildSeriesMutation.isPending}
                  className="border-amber-500/50 text-amber-400 hover:bg-amber-500/10 hover:border-amber-500/70"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${rebuildSeriesMutation.isPending ? 'animate-spin' : ''}`} />
                  {rebuildSeriesMutation.isPending ? 'Rebuilding...' : 'Rebuild Series'}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Books Row */}
      {books.length === 0 ? (
        <div className="text-center py-12">
          <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium text-foreground">No books found</h3>
          <p className="text-muted-foreground mt-1">
            This series doesn't have any books yet
          </p>
        </div>
      ) : (
        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">Books</h2>
          <div className="flex gap-5 overflow-x-auto pt-3 pb-4 scrollbar-hide -mx-4 px-5">
              {booksWithAvailability.map((book, index) => (
                <div key={book.id} className="flex-shrink-0 w-[140px] sm:w-[160px] relative">
                {/* Position Badge */}
                {((book as any).position ?? book.seriesPosition) != null && (
                  <div className="absolute -top-2.5 -left-2.5 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold shadow-lg ring-2 ring-background">
                    {(book as any).position ?? book.seriesPosition}
                  </div>
                )}
                <BookCard
                  book={book}
                  enableRequestStatus
                  requestStatus={requestStatusMap.get((book.hardcoverId ?? Number(book.id)) as number)}
                />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
