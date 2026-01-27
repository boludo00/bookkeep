import { useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, Library } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { hardcoverApi, requestsApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { BookRow } from '@/components/books/BookRow';
import { SeriesRow } from '@/components/series/SeriesRow';
import { toast } from 'sonner';

const BOOKS_PAGE_SIZE = 12;
const SERIES_PAGE_SIZE = 12;

export default function Author() {
  const [searchParams] = useSearchParams();
  const authorName = searchParams.get('name') || '';
  const [booksPage, setBooksPage] = useState(0);
  const [seriesPage, setSeriesPage] = useState(0);
  const [bioExpanded, setBioExpanded] = useState(false);
  const [requestingSeriesId, setRequestingSeriesId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['author', authorName, booksPage, seriesPage],
    queryFn: () =>
      hardcoverApi.getAuthor(authorName, {
        books_limit: BOOKS_PAGE_SIZE,
        books_offset: booksPage * BOOKS_PAGE_SIZE,
        series_limit: SERIES_PAGE_SIZE,
        series_offset: seriesPage * SERIES_PAGE_SIZE,
      }),
    enabled: !!authorName,
  });

  const author = data?.author;
  const books = useMemo(
    () => (data?.books || []).map(transformHardcoverBook),
    [data?.books]
  );
  const series = data?.series || [];
  const totalBooks = data?.books_total ?? 0;
  const totalSeries = data?.series_total ?? 0;
  const booksPages = Math.max(1, Math.ceil(totalBooks / BOOKS_PAGE_SIZE));
  const seriesPages = Math.max(1, Math.ceil(totalSeries / SERIES_PAGE_SIZE));

  const requestSeriesMutation = useMutation({
    mutationFn: (seriesId: number) => requestsApi.requestSeries(seriesId, 'ebook'),
    onMutate: (seriesId) => {
      setRequestingSeriesId(seriesId);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      toast.success('Series request submitted!', {
        description: `Requested ${data.requested_count} book(s). ${data.skipped_count} already available/requested.`,
      });
    },
    onError: (error: Error) => {
      toast.error('Failed to request series', {
        description: error.message,
      });
    },
    onSettled: () => {
      setRequestingSeriesId(null);
    },
  });

  if (!authorName) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Author Not Found</h1>
        <Link to="/search">
          <Button variant="outline">Back to Search</Button>
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-56 w-full rounded-2xl" />
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !author) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Author Not Found</h1>
        <p className="text-muted-foreground mb-4">
          We couldn't load details for "{authorName}".
        </p>
        <Link to="/search">
          <Button variant="outline">Back to Search</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <Link
        to="/search"
        className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Search
      </Link>

      <section className="relative rounded-2xl overflow-hidden">
        <div className="absolute inset-0">
          {author.image_url ? (
            <img
              src={author.image_url}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover opacity-30 blur-3xl scale-110 hidden md:block"
            />
          ) : (
            <div className="h-full w-full bg-gradient-to-r from-background via-background/90 to-background/60" />
          )}
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/80" />
        </div>

        <div className="relative flex flex-col md:flex-row gap-8 p-8">
          <div className="flex-shrink-0">
            <div className="h-40 w-40 rounded-2xl overflow-hidden bg-card/60 border border-border">
              {author.image_url ? (
                <img
                  src={author.image_url}
                  alt={author.name}
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="h-full w-full flex items-center justify-center text-muted-foreground text-sm">
                  No photo
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 space-y-4">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-foreground">{author.name}</h1>
              <div className="flex flex-wrap gap-3 mt-3 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  {totalBooks} books
                </span>
                <span className="inline-flex items-center gap-2">
                  <Library className="h-4 w-4" />
                  {totalSeries} series
                </span>
              </div>
            </div>

            <div className="max-w-3xl">
              <p
                className={`text-muted-foreground leading-relaxed ${
                  bioExpanded ? '' : 'line-clamp-4'
                }`}
              >
                {author.bio || 'No biography is available for this author yet.'}
              </p>
              {author.bio && author.bio.length > 240 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2 px-0 text-muted-foreground hover:text-foreground"
                  onClick={() => setBioExpanded((value) => !value)}
                >
                  {bioExpanded ? 'Show less' : 'Show more'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-foreground">Series</h2>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSeriesPage((value) => Math.min(value + 1, seriesPages - 1))}
              disabled={seriesPage + 1 >= seriesPages}
            >
              View more
            </Button>
            {seriesPages > 1 && (
              <span>
                Page {seriesPage + 1} of {seriesPages}
              </span>
            )}
          </div>
        </div>
        {series.length > 0 ? (
          <SeriesRow
            series={series}
            showRequest
            onRequestSeries={(seriesId) => requestSeriesMutation.mutate(seriesId)}
            requestingSeriesId={requestingSeriesId}
            requestDisabled={requestSeriesMutation.isPending}
          />
        ) : (
          <p className="text-muted-foreground">No series found for this author.</p>
        )}
        {seriesPages > 1 && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSeriesPage((value) => Math.max(value - 1, 0))}
              disabled={seriesPage === 0}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSeriesPage((value) => Math.min(value + 1, seriesPages - 1))}
              disabled={seriesPage + 1 >= seriesPages}
            >
              Next
            </Button>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-foreground">Books</h2>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setBooksPage((value) => Math.min(value + 1, booksPages - 1))}
              disabled={booksPage + 1 >= booksPages}
            >
              View more
            </Button>
            {booksPages > 1 && (
              <span>
                Page {booksPage + 1} of {booksPages}
              </span>
            )}
          </div>
        </div>
        {books.length > 0 ? (
          <BookRow books={books} />
        ) : (
          <p className="text-muted-foreground">No books found for this author.</p>
        )}
        {booksPages > 1 && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setBooksPage((value) => Math.max(value - 1, 0))}
              disabled={booksPage === 0}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setBooksPage((value) => Math.min(value + 1, booksPages - 1))}
              disabled={booksPage + 1 >= booksPages}
            >
              Next
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
