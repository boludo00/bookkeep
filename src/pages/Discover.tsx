import { BookRow } from '@/components/books/BookRow';
import { BookRowSkeleton } from '@/components/books/BookRowSkeleton';
import { RequestsRow } from '@/components/books/RequestsRow';
import { useTrendingBooks, usePopularBooks, useNewReleases } from '@/hooks/useHardcoverBooks';
import { useQuery } from '@tanstack/react-query';
import { requestsApi, settingsApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import type { BookRequest } from '@/types/book';
import { AlertCircle, Settings, ExternalLink, Sparkles, TrendingUp, Star, CalendarDays } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function Discover() {
  const { data: tokenStatus, isLoading: tokenLoading } = useQuery({
    queryKey: ['hardcover-token-status'],
    queryFn: () => settingsApi.getHardcoverToken(),
  });

  const { data: requests = [] } = useQuery({
    queryKey: ['requests', 'recent'],
    queryFn: () => requestsApi.getAll(0, 4),
    enabled: tokenStatus?.has_hardcover_token ?? false,
  });

  const recentRequests: BookRequest[] = requests
    .filter((req: any) => req.book)
    .map((req: any) => ({
      id: String(req.id),
      bookId: String(req.book?.hardcover_id || req.book_id),
      book: {
        id: String(req.book.id),
        title: req.book.title || 'Unknown Title',
        author: req.book.author || 'Unknown Author',
        cover: req.book.cover_url || '/placeholder.svg',
        description: req.book.description || '',
        publishedDate: req.book.published_date || '',
        genres: req.book.genres ? (typeof req.book.genres === 'string' ? req.book.genres.split(',') : req.book.genres) : [],
        rating: req.book.rating || 0,
        series: req.book.series,
        seriesPosition: req.book.series_position,
        hardcoverId: req.book.hardcover_id,
        hardcoverSlug: req.book.hardcover_slug,
        isbn: req.book.isbn,
        pageCount: req.book.page_count,
      },
      userId: String(req.user_id),
      userName: req.user?.username || req.user?.full_name || 'Unknown User',
      format: req.format,
      status: req.status,
      notes: req.notes,
      adminNotes: req.admin_notes,
      createdAt: req.created_at,
      updatedAt: req.updated_at,
    }));

  const { data: trendingBooks, isLoading: trendingLoading, error: trendingError } = useTrendingBooks(12);
  const { data: popularBooks, isLoading: popularLoading, error: popularError } = usePopularBooks(12);
  const { data: newReleases, isLoading: newLoading, error: newError } = useNewReleases(12);

  const discoverBooks = [
    ...(trendingBooks || []),
    ...(popularBooks || []),
    ...(newReleases || []),
  ];
  const discoverHardcoverIds = Array.from(
    new Set(
      discoverBooks
        .map((book) => book.hardcoverId ?? Number(book.id))
        .filter((bookId) => Number.isFinite(bookId))
        .map((bookId) => Number(bookId))
    )
  );

  const { data: discoverRequestStatuses } = useQuery({
    queryKey: ['requests', 'by-hardcover', 'discover', discoverHardcoverIds],
    queryFn: () => requestsApi.getByHardcoverBatch(discoverHardcoverIds),
    enabled: discoverHardcoverIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const discoverRequestStatusMap = new Map(
    discoverRequestStatuses?.results.map((item) => [item.hardcover_id, item]) ?? []
  );

  const hasError = trendingError || popularError || newError;
  const hasToken = tokenStatus?.has_hardcover_token ?? false;

  // Show splash page if no token
  if (!tokenLoading && !hasToken) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="max-w-2xl w-full bg-card/50 backdrop-blur-xl border-border/50 shadow-2xl">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20 shadow-lg shadow-primary/10">
              <Settings className="h-10 w-10 text-primary" />
            </div>
            <CardTitle className="text-3xl font-bold text-foreground tracking-tight">
              Hardcover API Token Required
            </CardTitle>
            <CardDescription className="text-base mt-3 text-muted-foreground">
              To discover books and browse the catalog, you need to configure your Hardcover API token.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 pt-4">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">
                Get your API token from{' '}
                <a
                  href="https://hardcover.app"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary font-medium hover:underline underline-offset-4 inline-flex items-center gap-1.5 transition-colors"
                >
                  hardcover.app
                  <ExternalLink className="h-3 w-3" />
                </a>
              </p>
            </div>
            <div className="flex justify-center pt-2">
              <Button asChild className="h-12 px-8 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium shadow-lg shadow-primary/20">
                <Link to="/settings">
                  <Settings className="h-4 w-4 mr-2" />
                  Go to Settings
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Hero section */}
      <div className="relative mb-10 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-8 overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-[100px]" />
        <div className="absolute top-0 right-1/4 w-64 h-64 bg-amber-500/5 rounded-full blur-[80px]" />

        <div className="relative">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <span className="text-sm font-medium text-primary uppercase tracking-wider">Welcome back</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-foreground tracking-tight">
            Discover Books
          </h1>
          <p className="mt-3 text-lg text-muted-foreground max-w-2xl">
            Explore trending titles, popular reads, and the latest releases. Your next favorite book is waiting.
          </p>
        </div>
      </div>

      {hasError && (
        <Alert variant="destructive" className="mb-6 rounded-xl border-rose-500/30 bg-rose-500/10">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to load some books. Please check your Hardcover API configuration in Settings.
          </AlertDescription>
        </Alert>
      )}

      {/* Trending */}
      {trendingLoading ? (
        <BookRowSkeleton title="Trending Now" />
      ) : trendingBooks && trendingBooks.length > 0 ? (
        <BookRow
          title="Trending Now"
          books={trendingBooks}
          viewAllLink="/browse/trending"
          requestStatusMap={discoverRequestStatusMap}
        />
      ) : null}

      {/* Recent Requests */}
      <RequestsRow
        title="Recent Requests"
        requests={recentRequests}
        viewAllLink="/requests"
      />

      {/* Popular */}
      {popularLoading ? (
        <BookRowSkeleton title="Popular This Month" />
      ) : popularBooks && popularBooks.length > 0 ? (
        <BookRow
          title="Popular This Month"
          books={popularBooks}
          viewAllLink="/browse/popular"
          requestStatusMap={discoverRequestStatusMap}
        />
      ) : null}

      {/* New Releases */}
      {newLoading ? (
        <BookRowSkeleton title="New Releases" />
      ) : newReleases && newReleases.length > 0 ? (
        <BookRow
          title="New Releases"
          books={newReleases}
          viewAllLink="/browse/new"
          requestStatusMap={discoverRequestStatusMap}
        />
      ) : null}
    </div>
  );
}
