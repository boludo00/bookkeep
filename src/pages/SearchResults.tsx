import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Search, Clock, Star, BookOpen, ArrowLeft } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { hardcoverApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RequestDialog } from '@/components/books/RequestDialog';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRating } from '@/lib/utils';
import type { Book } from '@/types/book';

export default function SearchResults() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const [requestBook, setRequestBook] = useState<Book | null>(null);

  const { data: searchData, isLoading, error } = useQuery({
    queryKey: ['search', query],
    queryFn: () => hardcoverApi.searchGrouped(query, 50),
    enabled: !!query && query.length > 0,
  });

  const books: Book[] = searchData?.books
    ? searchData.books.map(transformHardcoverBook)
    : [];
  const series = searchData?.series || [];
  const authors = searchData?.authors || [];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-8 w-64" />
        </div>
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

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold text-foreground mb-4">Search Error</h1>
        <p className="text-muted-foreground mb-4">
          {error instanceof Error ? error.message : 'Failed to search books'}
        </p>
        <Link to="/">
          <Button variant="outline">Go Back Home</Button>
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Discover
          </Link>
        </div>

        {/* Search Results Header */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Search className="h-5 w-5 text-muted-foreground" />
            <h1 className="text-2xl font-bold text-foreground">
              Search Results
            </h1>
          </div>
          {query && (
            <p className="text-muted-foreground">
              Found {books.length + series.length + authors.length} result
              {books.length + series.length + authors.length !== 1 ? 's' : ''} for "{query}"
            </p>
          )}
        </div>

        {/* Results */}
        {books.length === 0 && series.length === 0 && authors.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Search className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">No results found</h3>
            <p className="text-muted-foreground text-center max-w-md">
              We couldn't find any books matching "{query}". Try a different search term.
            </p>
          </div>
        ) : (
          <div className="space-y-10">
            {series.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-foreground mb-4">Series</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {series.map((item: any) => (
                    <Link
                      key={item.id}
                      to={`/series/${item.id}`}
                      className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-card hover:bg-accent/50 transition-colors"
                    >
                      <div>
                        <p className="font-semibold text-foreground">{item.name}</p>
                        {item.books_count != null && (
                          <p className="text-sm text-muted-foreground">
                            {item.books_count} books
                          </p>
                        )}
                      </div>
                      <ArrowLeft className="h-4 w-4 text-muted-foreground rotate-180" />
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {authors.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-foreground mb-4">Authors</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {authors.map((author: any) => (
                    <Link
                      key={author.name}
                      to={`/author?name=${encodeURIComponent(author.name)}`}
                      className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-card hover:bg-accent/50 transition-colors"
                    >
                      <div>
                        <p className="font-semibold text-foreground">{author.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {author.books_count} books
                        </p>
                      </div>
                      <ArrowLeft className="h-4 w-4 text-muted-foreground rotate-180" />
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {books.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-foreground mb-4">Books</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {books.map((book) => (
                    <div
                      key={book.id}
                      className="group relative flex gap-4 p-4 rounded-lg border border-border bg-card hover:bg-accent/50 transition-colors"
                    >
                      {/* Book Cover */}
                      <Link
                        to={`/book/${book.id}?bypass_cache=1`}
                        className="flex-shrink-0"
                      >
                        <img
                          src={book.cover}
                          alt={book.title}
                          loading="lazy"
                          className="w-20 h-28 object-cover rounded shadow-sm hover:shadow-md transition-shadow"
                        />
                      </Link>

                      {/* Book Info */}
                      <div className="flex-1 min-w-0 space-y-2">
                        <div>
                          <Link
                            to={`/book/${book.id}?bypass_cache=1`}
                            className="block"
                          >
                            <h3 className="font-semibold text-foreground line-clamp-2 hover:text-primary transition-colors">
                              {book.title}
                            </h3>
                          </Link>
                          <Link
                            to={`/author?name=${encodeURIComponent(book.author)}`}
                            className="text-sm text-muted-foreground mt-1 inline-flex hover:text-foreground transition-colors"
                          >
                            {book.author}
                          </Link>
                        </div>

                        {/* Metadata */}
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          {book.rating > 0 && (
                            <div className="flex items-center gap-1">
                              <Star className="h-3 w-3 fill-warning text-warning" />
                              <span className="font-medium">{formatRating(book.rating)}</span>
                            </div>
                          )}
                          {book.pageCount && (
                            <span>• {book.pageCount} pages</span>
                          )}
                          {book.publishedDate && (
                            <span>• {new Date(book.publishedDate).getFullYear()}</span>
                          )}
                        </div>

                        {/* Genres */}
                        {book.genres.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {book.genres.slice(0, 3).map((genre) => (
                              <Badge
                                key={genre}
                                variant="secondary"
                                className="text-xs"
                              >
                                {genre}
                              </Badge>
                            ))}
                          </div>
                        )}

                        {/* Series Info */}
                        {book.series && book.seriesPosition && (
                          <div className="text-xs text-muted-foreground">
                            <BookOpen className="h-3 w-3 inline mr-1" />
                            #{book.seriesPosition} in {book.series}
                          </div>
                        )}

                        {/* Description Preview */}
                        {book.description && (
                          <p className="text-sm text-muted-foreground line-clamp-2">
                            {book.description}
                          </p>
                        )}

                        {/* Request Button */}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setRequestBook(book)}
                          className="w-full mt-2"
                        >
                          <Clock className="h-4 w-4 mr-2" />
                          Request Book
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>

      {/* Request Dialog */}
      {requestBook && (
        <RequestDialog
          book={requestBook}
          open={!!requestBook}
          onOpenChange={(open) => !open && setRequestBook(null)}
        />
      )}
    </>
  );
}
