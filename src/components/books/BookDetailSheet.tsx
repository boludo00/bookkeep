import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Calendar, BookOpen, Tag, Clock, ArrowRight } from 'lucide-react';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RequestDialog } from '@/components/books/RequestDialog';
import { useQuery } from '@tanstack/react-query';
import { getBookDetails, transformHardcoverBook } from '@/lib/hardcover';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRating } from '@/lib/utils';
import type { Book } from '@/types/book';

interface BookDetailSheetProps {
  bookId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BookDetailSheet({ bookId, open, onOpenChange }: BookDetailSheetProps) {
  const [requestOpen, setRequestOpen] = useState(false);
  
  const { data: bookData, isLoading } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => getBookDetails(bookId),
    enabled: open && !!bookId,
  });

  const book: Book | undefined = bookData?.books_by_pk 
    ? transformHardcoverBook(bookData.books_by_pk)
    : undefined;

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
          {isLoading ? (
            <div className="space-y-6">
              <Skeleton className="h-8 w-3/4" />
              <div className="flex gap-6">
                <Skeleton className="w-32 h-48 rounded-lg" />
                <div className="flex-1 space-y-4">
                  <Skeleton className="h-6 w-full" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              </div>
            </div>
          ) : book ? (
            <div className="space-y-6">
              {/* Header */}
              <div>
                {book.series && book.seriesId && (
                  <Link
                    to={`/series/${book.seriesId}`}
                    className="inline-flex items-center gap-1 text-primary text-sm font-medium mb-2 hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenChange(false);
                    }}
                  >
                    {book.series} #{book.seriesPosition}
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                )}
                <h2 className="text-2xl font-bold text-foreground">{book.title}</h2>
                <Link
                  to={`/author?name=${encodeURIComponent(book.author)}`}
                  className="text-lg text-muted-foreground mt-1 inline-flex hover:text-foreground transition-colors"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenChange(false);
                  }}
                >
                  {book.author}
                </Link>
              </div>

              {/* Book Info */}
              <div className="flex gap-6">
                {/* Cover */}
                <div className="flex-shrink-0">
                  <img
                    src={book.cover}
                    alt={book.title}
                    loading="lazy"
                    className="w-32 rounded-lg shadow-lg"
                  />
                </div>

                {/* Meta */}
                <div className="flex-1 space-y-3">
                  <div className="flex flex-wrap gap-4 text-sm">
                    <div className="flex items-center gap-2 text-foreground">
                      <Star className="h-4 w-4 fill-warning text-warning" />
                      <span className="font-medium">{formatRating(book.rating)}</span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Calendar className="h-4 w-4" />
                      <span>{new Date(book.publishedDate).toLocaleDateString()}</span>
                    </div>
                    {book.pageCount && (
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <BookOpen className="h-4 w-4" />
                        <span>{book.pageCount} pages</span>
                      </div>
                    )}
                  </div>

                  {/* Genres */}
                  {book.genres && book.genres.length > 0 && (
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

                  {/* Actions */}
                  <div className="pt-2">
                    <Button
                      onClick={() => setRequestOpen(true)}
                      className="bg-primary hover:bg-primary/90"
                    >
                      <Clock className="h-4 w-4 mr-2" />
                      Request Book
                    </Button>
                  </div>
                </div>
              </div>

              {/* Description */}
              {book.description && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2">Description</h3>
                  <p className="text-muted-foreground leading-relaxed text-sm">
                    {book.description}
                  </p>
                </div>
              )}

              {/* View Full Page Link */}
              <div className="pt-4 border-t">
                <Link to={`/book/${book.id}`}>
                  <Button variant="outline" className="w-full">
                    View Full Page
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-muted-foreground">Book not found</p>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {book && (
        <RequestDialog
          book={book}
          open={requestOpen}
          onOpenChange={setRequestOpen}
        />
      )}
    </>
  );
}

