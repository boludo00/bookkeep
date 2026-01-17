import { useRef, useState } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Star, Calendar, BookOpen, Tag, Clock, Users, Headphones, Library, ExternalLink, Trash2 } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { RequestDialog } from '@/components/books/RequestDialog';
import { BookCard } from '@/components/books/BookCard';
import { useBookDetails, useBookPrompts } from '@/hooks/useHardcoverBooks';
import { requestsApi, readarrApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';

export default function BookDetails() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [requestOpen, setRequestOpen] = useState(false);
  const [promptViewCounts, setPromptViewCounts] = useState<Record<string, number>>({});
  const promptScrollLocks = useRef<Record<string, boolean>>({});
  const queryClient = useQueryClient();
  const { user } = useUser();
  const bypassCache =
    searchParams.get('bypass_cache') === 'true' || searchParams.get('bypass_cache') === '1';
  
  const { data: book, isLoading, error } = useBookDetails(id);
  const hardcoverId = book?.hardcoverId ?? (book?.id ? Number(book.id) : undefined);
  const hasHardcoverId = Number.isFinite(hardcoverId);

  const { data: requestStatus } = useQuery({
    queryKey: ['requests', 'by-hardcover', hardcoverId],
    queryFn: () => requestsApi.getByHardcoverId(hardcoverId as number),
    enabled: hasHardcoverId,
    staleTime: 15 * 1000, // Cache for 15 seconds - balanced for real-time updates
    refetchOnMount: true, // Refetch on mount but use cache if fresh
    refetchInterval: hasHardcoverId ? 30000 : false, // Poll every 30s instead of 15s
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
  });

  const hasAnyRequestsForReadarr = Boolean(requestStatus?.ebook || requestStatus?.audiobook);
  const { data: readarrManageLink } = useQuery({
    queryKey: ['readarr', 'manage-link', hardcoverId],
    queryFn: () => readarrApi.getManageLink(hardcoverId as number),
    enabled: hasHardcoverId && hasAnyRequestsForReadarr,
  });

  const { data: readarrAvailability } = useQuery({
    queryKey: ['readarr', 'availability', hardcoverId],
    queryFn: () => readarrApi.getAvailability(hardcoverId as number),
    enabled: hasHardcoverId,
    refetchInterval: hasHardcoverId ? 15000 : false,
  });

  const ebookRequestStatus = requestStatus?.ebook ?? null;
  const audiobookRequestStatus = requestStatus?.audiobook ?? null;
  const ebookRequestAvailable = ebookRequestStatus === 'available';
  const audiobookRequestAvailable = audiobookRequestStatus === 'available';

  const ebookReadarrBookId = requestStatus?.ebook_readarr_book_id;
  const audiobookReadarrBookId = requestStatus?.audiobook_readarr_book_id;
  const shouldCheckEbookReadarr =
    Boolean(ebookReadarrBookId) && ebookRequestStatus !== 'available';
  const shouldCheckAudiobookReadarr =
    Boolean(audiobookReadarrBookId) && audiobookRequestStatus !== 'available';

  const { data: ebookReadarrAvailability } = useQuery({
    queryKey: ['readarr', 'availability', 'readarr', ebookReadarrBookId],
    queryFn: () =>
      readarrApi.getAvailabilityByReadarrId(ebookReadarrBookId as number, 'ebook'),
    enabled: shouldCheckEbookReadarr,
    refetchInterval: shouldCheckEbookReadarr ? 15000 : false,
  });

  const { data: audiobookReadarrAvailability } = useQuery({
    queryKey: ['readarr', 'availability', 'readarr', audiobookReadarrBookId],
    queryFn: () =>
      readarrApi.getAvailabilityByReadarrId(audiobookReadarrBookId as number, 'audiobook'),
    enabled: shouldCheckAudiobookReadarr,
    refetchInterval: shouldCheckAudiobookReadarr ? 15000 : false,
  });

  const { data: promptSummaries = [] } = useBookPrompts(
    hasHardcoverId ? (hardcoverId as number) : undefined,
    4,
    30
  );

  const clearRequestsMutation = useMutation({
    mutationFn: async () => {
      if (!hasHardcoverId) {
        throw new Error('Book does not have a Hardcover ID.');
      }
      return requestsApi.clearByHardcoverId(hardcoverId as number);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover', hardcoverId] });
      toast.success('Request cleared', {
        description: `${data.deleted_count} request(s) removed.`,
      });
    },
    onError: (err: Error) => {
      toast.error('Failed to clear request', { description: err.message });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-6 w-32" />
        <div className="relative rounded-2xl overflow-hidden bg-card p-8">
          <div className="flex flex-col md:flex-row gap-8">
            <Skeleton className="w-48 md:w-56 h-80 rounded-xl mx-auto md:mx-0" />
            <div className="flex-1 space-y-4">
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-6 w-1/2" />
              <div className="flex gap-4">
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-5 w-20" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-6 w-16" />
                <Skeleton className="h-6 w-20" />
                <Skeleton className="h-6 w-18" />
              </div>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-10 w-36" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !book) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Book Not Found</h1>
        <p className="text-muted-foreground mb-4">
          {error?.message || "We couldn't find the book you're looking for."}
        </p>
        <Link to="/">
          <Button variant="outline">Go Back Home</Button>
        </Link>
      </div>
    );
  }

  const formatRating = (rating: number) => {
    return rating > 0 ? rating.toFixed(1) : 'N/A';
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Unknown';
    // Handle year-only format
    if (/^\d{4}$/.test(dateStr)) return dateStr;
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return dateStr;
    }
  };

  // Strip HTML tags from description
  const cleanDescription = (html: string) => {
    if (!html) return 'No description available.';
    return html.replace(/<[^>]*>/g, '').trim();
  };

  const ebookAvailable =
    book.ebookAvailable ||
    ebookRequestAvailable ||
    readarrAvailability?.ebook ||
    ebookReadarrAvailability?.available ||
    false;
  const audiobookAvailable =
    book.audiobookAvailable ||
    audiobookRequestAvailable ||
    readarrAvailability?.audiobook ||
    audiobookReadarrAvailability?.available ||
    false;
  const ebookNotFound = ebookRequestStatus === 'not_found';
  const audiobookNotFound = audiobookRequestStatus === 'not_found';
  const ebookRequested =
    Boolean(ebookRequestStatus) && !ebookNotFound && ebookRequestStatus !== 'available';
  const audiobookRequested =
    Boolean(audiobookRequestStatus) && !audiobookNotFound && audiobookRequestStatus !== 'available';
  const canRequestEbook = Boolean(user?.can_request_ebook) && !ebookAvailable;
  const canRequestAudiobook = Boolean(user?.can_request_audiobook) && !audiobookAvailable;
  const canRequestAnything = canRequestEbook || canRequestAudiobook;
  const hasMissingFormat = !ebookAvailable || !audiobookAvailable;
  const preferredFormat =
    ebookAvailable && !audiobookAvailable
      ? 'audiobook'
      : audiobookAvailable && !ebookAvailable
        ? 'ebook'
        : undefined;
  const hasAnyRequests = Boolean(ebookRequestStatus || audiobookRequestStatus);

  return (
    <>
      <div className="space-y-8">
        {/* Back Button */}
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Discover
        </Link>

        {/* Hero Section */}
        <div className="relative rounded-2xl overflow-hidden">
          {/* Background */}
          <div className="absolute inset-0">
            <img
              src={book.cover}
              alt=""
              className="h-full w-full object-cover opacity-30 blur-3xl scale-110"
            />
            <div className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/80" />
          </div>

          {/* Content */}
          <div className="relative flex flex-col md:flex-row gap-8 p-8">
            {/* Cover */}
            <div className="flex-shrink-0">
              <img
                src={book.cover}
                alt={book.title}
                className="w-48 md:w-56 rounded-xl shadow-2xl mx-auto md:mx-0"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = '/placeholder.svg';
                }}
              />
            </div>

            {/* Info */}
            <div className="flex-1 space-y-4">
              <div>
                {book.series && book.seriesId && (
                  <Link 
                    to={`/series/${book.seriesId}`}
                    className="text-primary text-sm font-medium mb-1 hover:underline"
                  >
                    {book.series} {book.seriesPosition ? `#${book.seriesPosition}` : ''}
                  </Link>
                )}
                <h1 className="text-3xl md:text-4xl font-bold text-foreground">
                  {book.title}
                </h1>
                <Link
                  to={`/author?name=${encodeURIComponent(book.author)}`}
                  className="text-xl text-primary mt-2 inline-flex underline-offset-4 hover:underline hover:text-primary/90 transition-colors"
                >
                  {book.author}
                </Link>
              </div>

              {/* Meta */}
              <div className="flex flex-wrap gap-4 text-sm">
                <div className="flex items-center gap-2 text-foreground">
                  <Star className="h-4 w-4 fill-warning text-warning" />
                  <span className="font-medium">{formatRating(book.rating)}</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Calendar className="h-4 w-4" />
                  <span>{formatDate(book.publishedDate)}</span>
                </div>
                {book.pageCount && book.pageCount > 0 && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <BookOpen className="h-4 w-4" />
                    <span>{book.pageCount} pages</span>
                  </div>
                )}
                {book.isbn && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="text-xs">ISBN: {book.isbn}</span>
                  </div>
                )}
              </div>

              {/* Genres */}
              {book.genres.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {book.genres.map((genre) => (
                    <Badge
                      key={genre}
                      variant="secondary"
                      className="bg-secondary/80 text-secondary-foreground"
                    >
                      <Tag className="h-3 w-3 mr-1" />
                      {genre}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Description */}
              <div className="max-w-2xl">
                <h2 className="text-lg font-semibold text-foreground mb-2">Description</h2>
                <p className="text-muted-foreground leading-relaxed">
                  {cleanDescription(book.description)}
                </p>
              </div>

              {/* Availability Badges */}
              <div className="flex flex-wrap gap-2 pt-2">
                {ebookAvailable && (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-500/30">
                    <BookOpen className="h-4 w-4 text-emerald-400" />
                    <span className="text-sm font-medium text-emerald-400">eBook Available</span>
                  </div>
                )}
                {audiobookAvailable && (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-500/30">
                    <BookOpen className="h-4 w-4 text-emerald-400" />
                    <span className="text-sm font-medium text-emerald-400">Audiobook Available</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex flex-wrap gap-3 pt-2">
                {!hasAnyRequests && hasMissingFormat && canRequestAnything && (
                  <Button
                    size="lg"
                    onClick={() => setRequestOpen(true)}
                    className="bg-primary hover:bg-primary/90 glow-primary"
                  >
                    <Clock className="h-4 w-4 mr-2" />
                    {preferredFormat === 'ebook'
                      ? 'Request eBook'
                      : preferredFormat === 'audiobook'
                        ? 'Request Audiobook'
                        : 'Request Book'}
                  </Button>
                )}
                {hasAnyRequests && !ebookAvailable && !audiobookAvailable && (
                  <div className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-2 text-sm font-medium text-primary">
                    <Clock className="h-4 w-4" />
                    Requested • Processing
                  </div>
                )}
                {book.hardcoverSlug && (
                  <Button
                    size="lg"
                    variant="outline"
                    asChild
                    className="border-border hover:bg-accent"
                  >
                    <a
                      href={`https://hardcover.app/books/${book.hardcoverSlug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      View on Hardcover
                    </a>
                  </Button>
                )}
                {hasAnyRequests && readarrManageLink?.url && readarrManageLink?.readarr_book_id && (
                  <Button
                    size="lg"
                    variant="outline"
                    asChild
                    className="border-border hover:bg-accent"
                  >
                    <a
                      href={readarrManageLink.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      Manage in Readarr
                    </a>
                  </Button>
                )}
                {hasAnyRequests && (
                  <Button
                    size="lg"
                    variant="outline"
                    onClick={() => clearRequestsMutation.mutate()}
                    disabled={clearRequestsMutation.isPending}
                    className="border-destructive/50 text-destructive hover:bg-destructive/10 hover:border-destructive"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    {clearRequestsMutation.isPending ? 'Clearing...' : 'Clear Request'}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {promptSummaries.length > 0 && (
          <section className="space-y-5">
            <div className="flex flex-col gap-2">
              <h2 className="text-xl font-bold text-foreground">Hardcover Prompts</h2>
              <p className="text-sm text-muted-foreground">
                Prompts this book appears in, with top picks from each.
              </p>
            </div>
            <div className="space-y-6">
              {promptSummaries.map((summary, index) => {
                const prompt = summary.prompt;
                const promptBooks = (prompt?.prompt_books || [])
                  .map((entry: any) => entry?.book ? transformHardcoverBook(entry.book) : null)
                  .filter((book): book is ReturnType<typeof transformHardcoverBook> => Boolean(book));
                const promptKey = String(prompt?.id ?? prompt?.slug ?? index);
                const defaultVisible = Math.min(10, promptBooks.length);
                const currentLimit = promptViewCounts[promptKey] ?? defaultVisible;
                const visibleBooks = promptBooks.slice(0, currentLimit);
                const hasMore = promptBooks.length > currentLimit;

                return (
                  <div
                    key={promptKey}
                    className="rounded-2xl border border-border bg-card/80 p-5"
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div className="space-y-2">
                        <p className="text-xs text-muted-foreground uppercase tracking-wide">
                          Hardcover Prompt
                        </p>
                        <h3 className="text-lg font-semibold text-foreground">
                          {prompt?.question || 'Discover similar reads'}
                        </h3>
                        {prompt?.description && (
                          <p className="text-sm text-muted-foreground line-clamp-2">
                            {prompt.description}
                          </p>
                        )}
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          {prompt?.answers_count != null && (
                            <span>{prompt.answers_count} answers</span>
                          )}
                          {prompt?.books_count != null && (
                            <span>{prompt.books_count} books</span>
                          )}
                          {prompt?.users_count != null && (
                            <span>{prompt.users_count} readers</span>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {hasMore ? 'Scroll to load more' : 'All books loaded'}
                      </div>
                    </div>
                    {visibleBooks.length > 0 && (
                      <div
                        className="mt-4 flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-2 px-2"
                        onScroll={(event) => {
                          if (!hasMore) return;
                          const container = event.currentTarget;
                          const threshold = 120;
                          const reachedEnd =
                            container.scrollLeft + container.clientWidth >=
                            container.scrollWidth - threshold;
                          if (!reachedEnd) return;
                          if (promptScrollLocks.current[promptKey]) return;
                          promptScrollLocks.current[promptKey] = true;
                          setPromptViewCounts((prev) => ({
                            ...prev,
                            [promptKey]: Math.min(
                              (prev[promptKey] ?? defaultVisible) + 10,
                              promptBooks.length
                            ),
                          }));
                          window.setTimeout(() => {
                            promptScrollLocks.current[promptKey] = false;
                          }, 200);
                        }}
                      >
                        {visibleBooks.map((promptBook) => (
                          <div
                            key={promptBook.id}
                            className="flex-shrink-0 w-[140px] sm:w-[160px]"
                          >
                            <BookCard book={promptBook} showRating={false} showRequestButton={false} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>

        <RequestDialog
          book={book}
          open={requestOpen}
          onOpenChange={setRequestOpen}
          preferredFormat={preferredFormat}
          disableFormats={{
            ebook: ebookAvailable,
            audiobook: audiobookAvailable,
          }}
        />
    </>
  );
}
