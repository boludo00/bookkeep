import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookCard } from '@/components/books/BookCard';
import { BookRowSkeleton } from '@/components/books/BookRowSkeleton';
import { useTrendingBooks, usePopularBooks, useNewReleases } from '@/hooks/useHardcoverBooks';
import { AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { requestsApi } from '@/lib/api';
import type { Book } from '@/types/book';

const categoryConfig = {
  trending: {
    title: 'Trending Now',
    description: 'Books that are making waves right now',
  },
  popular: {
    title: 'Popular This Month',
    description: 'Most popular books this month',
  },
  new: {
    title: 'New Releases',
    description: 'Recently published books',
  },
};

export default function Browse() {
  const { category } = useParams<{ category: string }>();
  
  const { data: trendingBooks, isLoading: trendingLoading, error: trendingError } = useTrendingBooks(50);
  const { data: popularBooks, isLoading: popularLoading, error: popularError } = usePopularBooks(50);
  const { data: newReleases, isLoading: newLoading, error: newError } = useNewReleases(50);

  const config = categoryConfig[category as keyof typeof categoryConfig] || categoryConfig.trending;
  
  let books;
  let isLoading;
  let error;

  switch (category) {
    case 'popular':
      books = popularBooks;
      isLoading = popularLoading;
      error = popularError;
      break;
    case 'new':
      books = newReleases;
      isLoading = newLoading;
      error = newError;
      break;
    case 'trending':
    default:
      books = trendingBooks;
      isLoading = trendingLoading;
      error = trendingError;
      break;
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{config.title}</h1>
          <p className="text-muted-foreground mt-1">{config.description}</p>
        </div>
        <BookRowSkeleton title="" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{config.title}</h1>
          <p className="text-muted-foreground mt-1">{config.description}</p>
        </div>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to load books. Please check your Hardcover API configuration in Settings.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{config.title}</h1>
        <p className="text-muted-foreground mt-1">{config.description}</p>
      </div>

      {books && books.length > 0 ? (
        <BrowseRequestStatusGrid books={books} />
      ) : (
        <div className="text-center py-12">
          <p className="text-muted-foreground">No books found</p>
        </div>
      )}
    </div>
  );
}

function BrowseRequestStatusGrid({ books }: { books: Book[] }) {
  const hardcoverIds = Array.from(
    new Set(
      books
        .map((book) => book.hardcoverId ?? Number(book.id))
        .filter((bookId) => Number.isFinite(bookId))
        .map((bookId) => Number(bookId))
    )
  );

  const { data: requestStatuses } = useQuery({
    queryKey: ['requests', 'by-hardcover', 'browse', hardcoverIds],
    queryFn: () => requestsApi.getByHardcoverBatch(hardcoverIds),
    enabled: hardcoverIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const requestStatusMap = new Map(
    requestStatuses?.results.map((item) => [item.hardcover_id, item]) ?? []
  );

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
      {books.map((book) => (
        <BookCard
          key={book.id}
          book={book}
          requestStatus={requestStatusMap.get((book.hardcoverId ?? Number(book.id)) as number)}
        />
      ))}
    </div>
  );
}
