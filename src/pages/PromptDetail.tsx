import { useState, useMemo, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Users, BookOpen as BookOpenIcon, Loader2 } from 'lucide-react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { BookCard } from '@/components/books/BookCard';
import { hardcoverApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';

export default function PromptDetail() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [displayLimit, setDisplayLimit] = useState(50); // Show 50 initially
  const loadMoreRef = useRef<HTMLDivElement>(null);

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['prompt-detail', slug],
    queryFn: async ({ pageParam = 0 }) => {
      if (!slug) throw new Error('Prompt slug required');
      // Fetch 1000 books per page
      const response = await hardcoverApi.getPromptBySlug(slug, 1000, pageParam, true);
      return response;
    },
    getNextPageParam: (lastPage, allPages) => {
      const totalFetched = allPages.reduce((sum, page) =>
        sum + (page.prompt.prompt_books?.length || 0), 0
      );
      const totalBooks = lastPage.prompt.books_count || 0;

      // If we've fetched everything, return undefined (no more pages)
      if (totalFetched >= totalBooks) return undefined;

      // Otherwise return the next offset
      return totalFetched;
    },
    enabled: !!slug,
    staleTime: 10 * 60 * 1000, // Cache for 10 minutes
    initialPageParam: 0,
  });

  const prompt = data?.pages[0]?.prompt;
  const totalBooks = prompt?.books_count || 0;

  // Combine all books from all pages
  const allBooks = useMemo(() => {
    if (!data?.pages) return [];

    const books: ReturnType<typeof transformHardcoverBook>[] = [];
    for (const page of data.pages) {
      const pageBooks = (page.prompt?.prompt_books || [])
        .map((entry: any) => entry?.book ? transformHardcoverBook(entry.book) : null)
        .filter((book): book is ReturnType<typeof transformHardcoverBook> => Boolean(book));
      books.push(...pageBooks);
    }
    return books;
  }, [data?.pages]);

  const totalFetchedBooks = allBooks.length;

  // Filter books based on search query (memoized)
  const filteredBooks = useMemo(() => {
    if (!searchQuery.trim()) return allBooks;

    const lowerQuery = searchQuery.toLowerCase();
    return allBooks.filter((book) =>
      book.title.toLowerCase().includes(lowerQuery) ||
      book.author.toLowerCase().includes(lowerQuery)
    );
  }, [allBooks, searchQuery]);

  // Paginate displayed books for performance
  const displayedBooks = filteredBooks.slice(0, displayLimit);
  const hasMoreToDisplay = filteredBooks.length > displayLimit;

  // Infinite scroll: Detect when user scrolls near bottom
  useEffect(() => {
    if (!loadMoreRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first.isIntersecting) {
          // User scrolled near bottom
          if (hasMoreToDisplay) {
            // Show more from already-fetched books
            setDisplayLimit((prev) => prev + 50);
          } else if (hasNextPage && !isFetchingNextPage && !searchQuery) {
            // Fetch more from API
            fetchNextPage();
          }
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(loadMoreRef.current);

    return () => observer.disconnect();
  }, [hasMoreToDisplay, hasNextPage, isFetchingNextPage, searchQuery, fetchNextPage]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton className="aspect-[2/3] w-full rounded-lg" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error || !prompt) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Prompt Not Found</h1>
        <p className="text-muted-foreground mb-4">
          {error instanceof Error ? error.message : "We couldn't find the prompt you're looking for."}
        </p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          Go Back
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Button
        variant="ghost"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      {/* Prompt Header */}
      <div className="rounded-2xl border border-border bg-card/80 p-6">
        <div className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">
              Hardcover Prompt
            </p>
            <h1 className="text-3xl font-bold text-foreground mb-3">
              {prompt.question}
            </h1>
            {prompt.description && (
              <p className="text-muted-foreground">
                {prompt.description}
              </p>
            )}
          </div>

          {/* Stats */}
          <div className="flex flex-wrap gap-4 text-sm">
            {prompt.answers_count != null && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Users className="h-4 w-4" />
                <span>{prompt.answers_count} answers</span>
              </div>
            )}
            {totalBooks != null && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <BookOpenIcon className="h-4 w-4" />
                <span>
                  {totalBooks} unique books
                  {totalFetchedBooks < totalBooks && (
                    <span className="text-xs ml-1">
                      (loaded {totalFetchedBooks})
                    </span>
                  )}
                </span>
              </div>
            )}
          </div>

          {/* Search */}
          <div className="pt-2">
            <input
              type="text"
              placeholder="Search books by title or author..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 rounded-lg border border-border bg-secondary/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="text-sm text-muted-foreground">
            Showing {displayedBooks.length} of {filteredBooks.length} books
            {searchQuery && filteredBooks.length !== allBooks.length && ` (filtered from ${allBooks.length})`}
          </div>
        </div>
      </div>

      {/* Books Grid */}
      {displayedBooks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12">
          <BookOpenIcon className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium text-foreground mb-2">No books found</h3>
          <p className="text-muted-foreground text-center max-w-md">
            {searchQuery.trim()
              ? `No books match "${searchQuery}"`
              : 'No books are associated with this prompt.'}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
            {displayedBooks.map((book) => (
              <BookCard key={book.id} book={book} showRating={true} showRequestButton={false} />
            ))}
          </div>

          {/* Infinite scroll trigger */}
          <div ref={loadMoreRef} className="flex justify-center py-8">
            {isFetchingNextPage && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Loading more books...</span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
