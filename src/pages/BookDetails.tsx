import { useState } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Star, Calendar, BookOpen, Tag, Clock, Users, Headphones, Library, ExternalLink, Trash2, Search, X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { RequestDialog } from '@/components/books/RequestDialog';
import { SearchReleaseDialog } from '@/components/books/SearchReleaseDialog';
import { BookCard } from '@/components/books/BookCard';
import { useBookDetails, useBookPrompts } from '@/hooks/useHardcoverBooks';
import { requestsApi, booksApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';

export default function BookDetails() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [requestOpen, setRequestOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchFormat, setSearchFormat] = useState<'ebook' | 'audiobook'>('ebook');
  const queryClient = useQueryClient();
  const { user } = useUser();
  const bypassCache =
    searchParams.get('bypass_cache') === 'true' || searchParams.get('bypass_cache') === '1';

  const { data: book, isLoading, error } = useBookDetails(id);
  const hardcoverId = book?.hardcoverId ?? (book?.id ? Number(book.id) : undefined);
  const hasHardcoverId = Number.isFinite(hardcoverId);

  const { data: dbBook } = useQuery({
    queryKey: ['book', 'by-hardcover', hardcoverId],
    queryFn: async () => {
      if (!hardcoverId) return null;
      const books = await booksApi.getAll(0, 1000);
      return books.find((b: any) => b.hardcover_id === hardcoverId) || null;
    },
    enabled: hasHardcoverId,
    staleTime: 5 * 1000,
    refetchInterval: hasHardcoverId ? 5000 : false,
  });

  const { data: requestStatus } = useQuery({
    queryKey: ['requests', 'by-hardcover', hardcoverId],
    queryFn: () => requestsApi.getByHardcoverId(hardcoverId as number),
    enabled: hasHardcoverId,
    staleTime: 15 * 1000,
    refetchOnMount: true,
    refetchInterval: hasHardcoverId ? 30000 : false,
    gcTime: 5 * 60 * 1000,
  });

  const ebookRequestStatus = requestStatus?.ebook ?? null;
  const audiobookRequestStatus = requestStatus?.audiobook ?? null;
  const ebookRequestAvailable = ebookRequestStatus === 'available';
  const audiobookRequestAvailable = audiobookRequestStatus === 'available';

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

  const clearAvailabilityMutation = useMutation({
    mutationFn: async ({ bookId, formatType }: { bookId: number; formatType: 'ebook' | 'audiobook' }) => {
      return booksApi.clearAvailability(bookId, formatType);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['book', 'by-hardcover', hardcoverId] });
      queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover', hardcoverId] });
      const formatName = variables.formatType === 'ebook' ? 'eBook' : 'Audiobook';
      toast.success('Availability cleared', {
        description: `${formatName} availability has been reset. You can now re-download this book.`,
      });
    },
    onError: (err: Error, variables) => {
      const formatName = variables.formatType === 'ebook' ? 'eBook' : 'Audiobook';
      toast.error('Failed to clear availability', {
        description: `Could not clear ${formatName} availability: ${err.message}`
      });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <Skeleton className="h-6 w-32 rounded-lg" />
        <div className="relative rounded-2xl overflow-hidden bg-card/50 p-8">
          <div className="flex flex-col md:flex-row gap-8">
            <Skeleton className="w-48 md:w-56 h-80 rounded-xl mx-auto md:mx-0" />
            <div className="flex-1 space-y-4">
              <Skeleton className="h-10 w-3/4 rounded-lg" />
              <Skeleton className="h-6 w-1/2 rounded-lg" />
              <div className="flex gap-4">
                <Skeleton className="h-5 w-20 rounded-lg" />
                <Skeleton className="h-5 w-24 rounded-lg" />
                <Skeleton className="h-5 w-20 rounded-lg" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-7 w-16 rounded-lg" />
                <Skeleton className="h-7 w-20 rounded-lg" />
                <Skeleton className="h-7 w-18 rounded-lg" />
              </div>
              <Skeleton className="h-32 w-full rounded-lg" />
              <Skeleton className="h-12 w-40 rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !book) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-muted/30 mb-6">
          <BookOpen className="h-10 w-10 text-muted-foreground/50" />
        </div>
        <h1 className="text-2xl font-bold text-foreground mb-3">Book Not Found</h1>
        <p className="text-muted-foreground mb-6 text-center max-w-md">
          {error?.message || "We couldn't find the book you're looking for."}
        </p>
        <Link to="/">
          <Button variant="outline" className="h-11 px-6 rounded-xl">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Go Back Home
          </Button>
        </Link>
      </div>
    );
  }

  const formatRating = (rating: number) => {
    return rating > 0 ? rating.toFixed(1) : 'N/A';
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Unknown';
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

  const cleanDescription = (html: string) => {
    if (!html) return 'No description available.';
    return html.replace(/<[^>]*>/g, '').trim();
  };

  const ebookAvailable =
    dbBook?.ebook_available ||
    book.ebookAvailable ||
    ebookRequestAvailable ||
    false;
  const audiobookAvailable =
    dbBook?.audiobook_available ||
    book.audiobookAvailable ||
    audiobookRequestAvailable ||
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
  const canDownload = Boolean(user?.can_download);
  const hasMissingFormat = !ebookAvailable || !audiobookAvailable;
  const preferredFormat =
    ebookAvailable && !audiobookAvailable
      ? 'audiobook'
      : audiobookAvailable && !ebookAvailable
        ? 'ebook'
        : undefined;
  const hasAnyRequests = ebookRequested || audiobookRequested;

  return (
    <>
      <div className="space-y-10 animate-fade-in-up">
        {/* Back Button */}
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-muted-foreground hover:text-primary transition-colors duration-300 group"
        >
          <ArrowLeft className="h-4 w-4 transition-transform duration-300 group-hover:-translate-x-1" />
          <span className="font-medium">Back to Discover</span>
        </Link>

        {/* Hero Section */}
        <div className="relative rounded-3xl overflow-hidden">
          {/* Blurred cover background */}
          <div className="absolute inset-0">
            <img
              src={book.cover}
              alt=""
              className="h-full w-full object-cover opacity-20 blur-3xl scale-125"
            />
            <div className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/80" />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-background/50" />
          </div>

          {/* Content */}
          <div className="relative flex flex-col md:flex-row gap-8 lg:gap-12 p-6 md:p-10">
            {/* Cover */}
            <div className="flex-shrink-0 mx-auto md:mx-0">
              <div className="book-cover-glow">
                <div className="book-cover w-52 md:w-64 aspect-[2/3]">
                  <img
                    src={book.cover}
                    alt={book.title}
                    className="h-full w-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = '/placeholder.svg';
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Info */}
            <div className="flex-1 space-y-5 text-center md:text-left">
              {/* Series link */}
              {book.series && book.seriesId && (
                <Link
                  to={`/series/${book.seriesId}`}
                  className="inline-flex items-center gap-2 text-primary text-sm font-medium hover:underline underline-offset-4"
                >
                  {book.series} {book.seriesPosition ? `#${book.seriesPosition}` : ''}
                </Link>
              )}

              {/* Title */}
              <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground tracking-tight leading-tight">
                {book.title}
              </h1>

              {/* Author */}
              <Link
                to={`/author?name=${encodeURIComponent(book.author)}`}
                className="inline-block text-xl text-primary font-medium hover:underline underline-offset-4 transition-colors"
              >
                {book.author}
              </Link>

              {/* Meta info */}
              <div className="flex flex-wrap justify-center md:justify-start gap-5 text-sm">
                <div className="flex items-center gap-2">
                  <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                  <span className="font-semibold text-foreground">{formatRating(book.rating)}</span>
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
                    <span className="text-xs font-mono">ISBN: {book.isbn}</span>
                  </div>
                )}
              </div>

              {/* Genres */}
              {book.genres.length > 0 && (
                <div className="flex flex-wrap justify-center md:justify-start gap-2">
                  {book.genres.map((genre) => (
                    <Badge
                      key={genre}
                      variant="secondary"
                      className="px-3 py-1 rounded-lg bg-muted/50 border-border/50 text-muted-foreground font-medium"
                    >
                      {genre}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Description */}
              <div className="max-w-2xl">
                <h2 className="text-lg font-semibold text-foreground mb-3">Description</h2>
                <p className="text-muted-foreground leading-relaxed">
                  {cleanDescription(book.description)}
                </p>
              </div>

              {/* Availability badges */}
              <div className="flex flex-wrap justify-center md:justify-start gap-2 pt-2">
                {ebookAvailable && (
                  <div className="group flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                    <BookOpen className="h-4 w-4 text-emerald-400" />
                    <span className="text-sm font-medium text-emerald-400">eBook Available</span>
                    {dbBook?.id && dbBook.ebook_available && (
                      <button
                        onClick={() => {
                          if (window.confirm('Clear eBook availability? This will allow you to re-download this book.')) {
                            clearAvailabilityMutation.mutate({ bookId: dbBook.id, formatType: 'ebook' });
                          }
                        }}
                        className="ml-1 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-emerald-500/20 rounded-lg"
                        title="Clear eBook availability"
                      >
                        <X className="h-3 w-3 text-emerald-400" />
                      </button>
                    )}
                  </div>
                )}
                {audiobookAvailable && (
                  <div className="group flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-500/10 border border-violet-500/30">
                    <Headphones className="h-4 w-4 text-violet-400" />
                    <span className="text-sm font-medium text-violet-400">Audiobook Available</span>
                    {dbBook?.id && dbBook.audiobook_available && (
                      <button
                        onClick={() => {
                          if (window.confirm('Clear audiobook availability? This will allow you to re-download this book.')) {
                            clearAvailabilityMutation.mutate({ bookId: dbBook.id, formatType: 'audiobook' });
                          }
                        }}
                        className="ml-1 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-violet-500/20 rounded-lg"
                        title="Clear audiobook availability"
                      >
                        <X className="h-3 w-3 text-violet-400" />
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap justify-center md:justify-start gap-3 pt-4">
                {!hasAnyRequests && hasMissingFormat && canRequestAnything && (
                  <>
                    <Button
                      size="lg"
                      onClick={() => setRequestOpen(true)}
                      className="h-12 px-6 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium shadow-lg shadow-primary/25 transition-all duration-300 hover:shadow-primary/40"
                    >
                      <Clock className="h-4 w-4 mr-2" />
                      {preferredFormat === 'ebook'
                        ? 'Request eBook'
                        : preferredFormat === 'audiobook'
                          ? 'Request Audiobook'
                          : 'Request Book'}
                    </Button>
                    {canDownload && (
                      <Button
                        size="lg"
                        variant="outline"
                        onClick={() => {
                          setSearchFormat(preferredFormat || 'ebook');
                          setSearchOpen(true);
                        }}
                        className="h-12 px-6 rounded-xl border-border/50 hover:bg-card hover:border-primary/30"
                      >
                        <Search className="h-4 w-4 mr-2" />
                        Search Book
                      </Button>
                    )}
                  </>
                )}
                {hasAnyRequests && !ebookAvailable && !audiobookAvailable && (
                  <div className="inline-flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-5 py-3 text-sm font-medium text-amber-400">
                    <Clock className="h-4 w-4" />
                    Requested • Processing
                  </div>
                )}
                {book.hardcoverSlug && (
                  <Button
                    size="lg"
                    variant="outline"
                    asChild
                    className="h-12 px-6 rounded-xl border-border/50 hover:bg-card hover:border-primary/30"
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
                {hasAnyRequests && (
                  <Button
                    size="lg"
                    variant="outline"
                    onClick={() => clearRequestsMutation.mutate()}
                    disabled={clearRequestsMutation.isPending}
                    className="h-12 px-6 rounded-xl border-rose-500/30 text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/50"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    {clearRequestsMutation.isPending ? 'Clearing...' : 'Clear Request'}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Hardcover Prompts */}
        {promptSummaries.length > 0 && (
          <section className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-foreground tracking-tight">
                Hardcover Prompts
              </h2>
              <p className="text-sm text-muted-foreground mt-2">
                Prompts this book appears in, with top picks from each.
              </p>
            </div>
            <div className="space-y-6">
              {promptSummaries.map((summary, index) => {
                const prompt = summary.prompt;
                const promptBooks = (prompt?.prompt_books || [])
                  .map((entry: any) => entry?.book ? transformHardcoverBook(entry.book) : null)
                  .filter((book): book is ReturnType<typeof transformHardcoverBook> => Boolean(book));
                const defaultVisible = Math.min(10, promptBooks.length);
                const visibleBooks = promptBooks.slice(0, defaultVisible);
                const promptKey = String(prompt?.id ?? prompt?.slug ?? index);

                return (
                  <div
                    key={promptKey}
                    className="rounded-2xl border border-border/50 bg-card/30 backdrop-blur-sm p-6 animate-fade-in-up"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div className="space-y-2 flex-1">
                        <p className="text-xs text-primary uppercase tracking-wider font-medium">
                          Hardcover Prompt
                        </p>
                        <h3 className="text-xl font-semibold text-foreground">
                          {prompt?.question || 'Discover similar reads'}
                        </h3>
                        {prompt?.description && (
                          <p className="text-sm text-muted-foreground line-clamp-2">
                            {prompt.description}
                          </p>
                        )}
                        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
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
                      {prompt?.slug && promptBooks.length > defaultVisible && (
                        <Link to={`/prompt/${prompt.slug}`}>
                          <Button variant="outline" size="sm" className="rounded-lg">
                            {prompt.books_count && prompt.books_count > promptBooks.length
                              ? `View More (${prompt.books_count} total)`
                              : `View All ${promptBooks.length} Books`}
                          </Button>
                        </Link>
                      )}
                    </div>
                    {visibleBooks.length > 0 && (
                      <div className="mt-6 flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-2 px-2">
                        {visibleBooks.map((promptBook) => (
                          <div
                            key={promptBook.id}
                            className="flex-shrink-0 w-[130px] sm:w-[150px]"
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

      {searchOpen && (
        <SearchReleaseDialog
          book={{
            id: dbBook?.id ?? requestStatus?.book_id ?? undefined,
            hardcoverId: hardcoverId,
            title: book.title,
            author: book.author,
            isbn: book.isbn,
            description: book.description,
            cover: book.cover,
            publishedDate: book.publishedDate,
            rating: book.rating,
            pageCount: book.pageCount,
            series: book.series,
            seriesPosition: book.seriesPosition,
            genres: book.genres,
          }}
          open={searchOpen}
          onOpenChange={setSearchOpen}
          formatType={searchFormat}
        />
      )}
    </>
  );
}
