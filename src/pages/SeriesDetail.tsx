import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, Download, Loader2, Trash2, RefreshCw } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSeriesBooks, normalizeSeriesBooks, rebuildSeries } from '@/lib/hardcover';
import { requestsApi, booksApi } from '@/lib/api';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { BookCard } from '@/components/books/BookCard';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';
import type { Book } from '@/types/book';

export default function SeriesDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [requestFormat, setRequestFormat] = useState<'ebook' | 'audiobook'>('ebook');
  const [seriesView, setSeriesView] = useState<'original' | 'expanded'>('original');
  const { isAdmin } = useUser();
  const autoRefreshRef = useRef(false);
  
  const { data: seriesData, isLoading, error } = useQuery({
    queryKey: ['series', id],
    queryFn: () => getSeriesBooks(Number(id)),
    enabled: !!id && !isNaN(Number(id)),
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

  // Count available/requested books
  const availableCount = books.filter(b => b.ebookAvailable || b.audiobookAvailable).length;
  const missingCount = books.length - availableCount;

  // Request series mutation
  const requestSeriesMutation = useMutation({
    mutationFn: (format: 'ebook' | 'audiobook') => 
      requestsApi.requestSeries(Number(id), format),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      queryClient.invalidateQueries({ queryKey: ['series', id] });
      toast.success('Series request submitted!', {
        description: `Requested ${data.requested_count} book(s). ${data.skipped_count} already available/requested.`,
      });
    },
    onError: (error: Error) => {
      toast.error('Failed to request series', {
        description: error.message,
      });
    },
  });

  // Clear series requests mutation
  const clearSeriesMutation = useMutation({
    mutationFn: () => requestsApi.clearSeries(Number(id)),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      queryClient.invalidateQueries({ queryKey: ['series', id] });
      toast.success('Series requests cleared!', {
        description: `Cleared ${data.deleted_count} request(s) from ${data.affected_books} book(s).`,
      });
    },
    onError: (error: Error) => {
      toast.error('Failed to clear series requests', {
        description: error.message,
      });
    },
  });

  // Refresh series availability mutation
  const refreshSeriesMutation = useMutation({
    mutationFn: () => booksApi.refreshSeriesAvailability(Number(id)),
    onSuccess: async (data) => {
      const freshSeries = await getSeriesBooks(Number(id), { bypassCache: true });
      queryClient.setQueryData(['series', id], freshSeries);
      queryClient.invalidateQueries({ queryKey: ['popular-series'] });
      toast.success('Series availability refreshed!', {
        description: `${data.ebooks_available} eBook(s) and ${data.audiobooks_available} audiobook(s) found out of ${data.total_books} books.`,
      });
    },
    onError: (error: Error) => {
      toast.error('Failed to refresh series availability', {
        description: error.message,
      });
    },
  });

  useEffect(() => {
    if (!series || !id || autoRefreshRef.current) return;
    if (!allBooks.length) return;
    autoRefreshRef.current = true;
    booksApi.refreshSeriesAvailability(Number(id))
      .then(() => getSeriesBooks(Number(id), { bypassCache: true }))
      .then((freshSeries) => {
        queryClient.setQueryData(['series', id], freshSeries);
        queryClient.invalidateQueries({ queryKey: ['popular-series'] });
      })
      .catch(() => {
        autoRefreshRef.current = false;
      });
  }, [series, id, allBooks.length, queryClient]);

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

  // Check if there are any requests to clear (books that are requested but not available)
  const requestedCount = books.filter(b => {
    const isAvailable = b.ebookAvailable || b.audiobookAvailable;
    return !isAvailable; // Could have requests if not available
  }).length - missingCount; // Approximation - actual count would need API call
  
  // For now, show clear button if there are any non-available books
  const hasRequests = books.length > availableCount;

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
        {/* Blurred Background */}
        <div className="absolute inset-0">
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
              {missingCount > 0 && (
                <Badge variant="secondary" className="bg-amber-500/20 text-amber-400 border-amber-500/30">
                  {missingCount} Not Available
                </Badge>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap gap-3 pt-2">
              {/* Request Series Button */}
              {missingCount > 0 && (
                <Button
                  size="lg"
                  onClick={() => requestSeriesMutation.mutate('ebook')}
                  disabled={requestSeriesMutation.isPending || clearSeriesMutation.isPending}
                  className="bg-primary hover:bg-primary/90 glow-primary"
                >
                  {requestSeriesMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4 mr-2" />
                  )}
                  Request Series ({missingCount} book{missingCount !== 1 ? 's' : ''})
                </Button>
              )}
              
              {/* Clear Requests Button */}
              {hasRequests && (
                <Button
                  size="lg"
                  variant="outline"
                  onClick={() => clearSeriesMutation.mutate()}
                  disabled={clearSeriesMutation.isPending || requestSeriesMutation.isPending || refreshSeriesMutation.isPending}
                  className="border-destructive/50 text-destructive hover:bg-destructive/10 hover:border-destructive"
                >
                  {clearSeriesMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Clear Requests
                </Button>
              )}
              
              {/* Scan Library Button */}
              <Button
                size="lg"
                variant="outline"
                onClick={() => refreshSeriesMutation.mutate()}
                disabled={refreshSeriesMutation.isPending || requestSeriesMutation.isPending || clearSeriesMutation.isPending}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${refreshSeriesMutation.isPending ? 'animate-spin' : ''}`} />
                {refreshSeriesMutation.isPending ? 'Scanning...' : 'Scan Library'}
              </Button>

              {isAdmin && (
                <Button
                  size="lg"
                  variant="outline"
                  onClick={() => rebuildSeriesMutation.mutate()}
                  disabled={
                    rebuildSeriesMutation.isPending ||
                    requestSeriesMutation.isPending ||
                    clearSeriesMutation.isPending ||
                    refreshSeriesMutation.isPending
                  }
                  className="border-amber-500/50 text-amber-400 hover:bg-amber-500/10 hover:border-amber-500/70"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${rebuildSeriesMutation.isPending ? 'animate-spin' : ''}`} />
                  {rebuildSeriesMutation.isPending ? 'Rebuilding...' : 'Rebuild Series'}
                </Button>
              )}
            </div>

            {missingCount === 0 && books.length > 0 && (
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/20 border border-emerald-500/30 w-fit">
                <BookOpen className="h-5 w-5 text-emerald-400" />
                <span className="font-medium text-emerald-400">Complete Series Available</span>
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
          <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-4 px-4">
            {books.map((book, index) => (
              <div key={book.id} className="flex-shrink-0 w-[140px] sm:w-[160px] relative">
                {/* Position Badge */}
                {((book as any).position ?? book.seriesPosition) != null && (
                  <div className="absolute -top-2 -left-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold shadow-lg">
                    {(book as any).position ?? book.seriesPosition}
                  </div>
                )}
                <BookCard book={book} />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
