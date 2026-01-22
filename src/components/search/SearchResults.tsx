import { Link } from 'react-router-dom';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Book } from '@/types/book';

interface SearchGroupedResults {
  series: Array<{ id: number; name: string; books_count?: number | null }>;
  authors: Array<{ name: string; books_count: number }>;
  books: Book[];
}

interface SearchResultsProps {
  results: SearchGroupedResults;
  query: string;
  isLoading?: boolean;
  isFetched?: boolean;
}

export function SearchResults({ results, query, isLoading, isFetched }: SearchResultsProps) {
  if (isLoading) {
    return (
      <div className="absolute top-full left-0 right-0 mt-2 rounded-lg bg-popover border border-border shadow-xl p-4">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
          Searching…
        </div>
      </div>
    );
  }

  const hasResults =
    results.series.length > 0 || results.authors.length > 0 || results.books.length > 0;

  if (!hasResults && isFetched) {
    return (
      <div className="absolute top-full left-0 right-0 mt-2 rounded-lg bg-popover border border-border shadow-xl p-4">
        <p className="text-sm text-muted-foreground">
          No results found for "{query}"
        </p>
      </div>
    );
  }

  if (!hasResults) {
    return null;
  }

  return (
    <div className="absolute top-full left-0 right-0 mt-2 rounded-lg bg-popover border border-border shadow-xl z-50">
      <ScrollArea className="max-h-[60vh]">
      {results.series.length > 0 && (
        <div className="border-b border-border/60">
          <div className="px-3 pt-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Series
          </div>
          {results.series.map((series) => (
            <Link
              key={series.id}
              to={`/series/${series.id}`}
              className="flex items-center justify-between gap-4 px-3 py-2 hover:bg-muted transition-colors"
            >
              <span className="font-medium text-foreground truncate">{series.name}</span>
              {series.books_count != null && (
                <span className="text-xs text-muted-foreground">{series.books_count} books</span>
              )}
            </Link>
          ))}
        </div>
      )}

      {results.authors.length > 0 && (
        <div className="border-b border-border/60">
          <div className="px-3 pt-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Authors
          </div>
          {results.authors.map((author) => (
            <Link
              key={author.name}
              to={`/author?name=${encodeURIComponent(author.name)}`}
              className="flex items-center justify-between gap-4 px-3 py-2 hover:bg-muted transition-colors"
            >
              <span className="font-medium text-foreground truncate">{author.name}</span>
              <span className="text-xs text-muted-foreground">{author.books_count} books</span>
            </Link>
          ))}
        </div>
      )}

      {results.books.length > 0 && (
        <div>
          <div className="px-3 pt-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Books
          </div>
          {results.books.map((book) => (
            <Link
              key={book.id}
              to={`/book/${book.id}?bypass_cache=1`}
              className="flex items-center gap-4 p-3 hover:bg-muted transition-colors"
            >
              <img
                src={book.cover}
                alt={book.title}
                className="h-16 w-11 rounded object-cover"
              />
              <div className="flex-1 min-w-0">
                <h4 className="font-medium text-foreground truncate">{book.title}</h4>
                <p className="text-sm text-muted-foreground">{book.author}</p>
                <div className="flex gap-2 mt-1">
                  {book.genres.slice(0, 2).map((genre) => (
                    <span
                      key={genre}
                      className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary"
                    >
                      {genre}
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      </ScrollArea>
    </div>
  );
}
