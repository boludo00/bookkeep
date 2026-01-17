import { BookRow } from '@/components/books/BookRow';
import { BookRowSkeleton } from '@/components/books/BookRowSkeleton';
import { RequestsRow } from '@/components/books/RequestsRow';
import { useTrendingBooks, usePopularBooks, useNewReleases } from '@/hooks/useHardcoverBooks';
import { useQuery } from '@tanstack/react-query';
import { requestsApi, settingsApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import type { BookRequest } from '@/types/book';
import { AlertCircle, Settings, ExternalLink } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function Discover() {
  // Check if Hardcover token is configured
  const { data: tokenStatus, isLoading: tokenLoading } = useQuery({
    queryKey: ['hardcover-token-status'],
    queryFn: () => settingsApi.getHardcoverToken(),
  });

  const { data: requests = [] } = useQuery({
    queryKey: ['requests', 'recent'],
    queryFn: () => requestsApi.getAll(0, 4),
    enabled: tokenStatus?.has_hardcover_token ?? false,
  });

  // Filter out requests without books to prevent UI issues
  const recentRequests: BookRequest[] = requests
    .filter((req: any) => req.book) // Only include requests with associated books
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
        <Card className="max-w-2xl w-full bg-card border-border">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
              <Settings className="h-8 w-8 text-primary" />
            </div>
            <CardTitle className="text-2xl text-foreground">Hardcover API Token Required</CardTitle>
            <CardDescription className="text-base mt-2">
              To discover books and browse the catalog, you need to configure your Hardcover API token.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 text-center">
              <p className="text-sm text-muted-foreground">
                Get your API token from{' '}
                <a
                  href="https://hardcover.app"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  hardcover.app
                  <ExternalLink className="h-3 w-3" />
                </a>
              </p>
            </div>
            <div className="flex justify-center pt-4">
              <Button asChild className="bg-primary hover:bg-primary/90">
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
    <div className="space-y-2">
      {hasError && (
        <Alert variant="destructive" className="mb-4">
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
