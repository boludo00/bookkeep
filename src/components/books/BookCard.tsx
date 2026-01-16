import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Clock, BookOpen, Headphones } from 'lucide-react';
import { cn, formatRating } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { RequestDialog } from '@/components/books/RequestDialog';
import { useQuery } from '@tanstack/react-query';
import { requestsApi } from '@/lib/api';
import type { Book } from '@/types/book';

interface BookCardProps {
  book: Book;
  status?: 'available' | 'requested' | 'none';
  showRating?: boolean;
  enableRequestStatus?: boolean;
  showRequestButton?: boolean;
  requestStatus?: { ebook?: string | null; audiobook?: string | null };
}

export function BookCard({
  book,
  status = 'none',
  showRating = true,
  enableRequestStatus = false,
  showRequestButton = true,
  requestStatus,
}: BookCardProps) {
  const [requestOpen, setRequestOpen] = useState(false);
  const { data: existingRequests } = useQuery({
    queryKey: ['book-requests', book.hardcoverId],
    queryFn: () =>
      book.hardcoverId
        ? requestsApi.getByHardcoverId(book.hardcoverId)
        : Promise.resolve({ ebook: null, audiobook: null, book_id: null }),
    enabled: enableRequestStatus && !!book.hardcoverId,
    staleTime: 60 * 1000,
  });
  const ebookAvailable = book.ebookAvailable || false;
  const audiobookAvailable = book.audiobookAvailable || false;
  const isAnyFormatAvailable = ebookAvailable || audiobookAvailable;
  const statusSource = requestStatus || (enableRequestStatus ? existingRequests : null);
  const requestStatuses = statusSource
    ? [statusSource.ebook, statusSource.audiobook].filter((value): value is string => !!value)
    : [];
  const hasActiveRequest = enableRequestStatus
    ? requestStatuses.some((value) => value !== 'not_found' && value !== 'available')
    : false;
  const effectiveStatus = status !== 'none' ? status : hasActiveRequest ? 'requested' : 'none';
  const bookLink = book.seriesId
    ? `/book/${book.id}?seriesId=${book.seriesId}`
    : `/book/${book.id}`;
  
  return (
    <>
      <div className="group relative overflow-hidden rounded-lg card-hover">
        <Link to={bookLink} className="block">
          {/* Cover Image */}
          <div className="aspect-[2/3] overflow-hidden rounded-lg bg-card">
            <img
              src={book.cover}
              alt={book.title}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
            
            {/* Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-background/90 via-background/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            
            {/* Format Availability Badges - Top Right */}
            {isAnyFormatAvailable && (
              <div className="absolute top-2 right-2 flex gap-1">
                {ebookAvailable && (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg" title="eBook Available">
                    <BookOpen className="h-4 w-4" />
                  </div>
                )}
                {audiobookAvailable && (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-500 text-white shadow-lg" title="Audiobook Available">
                    <Headphones className="h-4 w-4" />
                  </div>
                )}
              </div>
            )}
            
            {/* Requested Badge - only show if not available */}
        {!isAnyFormatAvailable && effectiveStatus === 'requested' && (
          <div className="absolute top-2 right-2">
            <div
              className="flex h-7 w-7 items-center justify-center rounded-full bg-warning text-warning-foreground"
              title="Requested"
            >
              <Clock className="h-4 w-4" />
            </div>
          </div>
        )}

            {/* Genre Badge */}
            <div className="absolute top-2 left-2">
              <span className="rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground">
                {book.genres[0]}
              </span>
            </div>

            {/* Hover Info */}
            <div className="absolute bottom-0 left-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <h3 className="font-semibold text-foreground line-clamp-2">{book.title}</h3>
              <p className="text-sm text-muted-foreground mt-1">{book.author}</p>
              {showRating && (
                <div className="flex items-center gap-1 mt-2">
                  <Star className="h-4 w-4 fill-warning text-warning" />
                  <span className="text-sm font-medium text-foreground">{formatRating(book.rating)}</span>
                </div>
              )}
            </div>
          </div>
        </Link>

        {!isAnyFormatAvailable && showRequestButton && (
          <div className="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <Button
              size="sm"
              className="bg-primary/90 hover:bg-primary"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setRequestOpen(true);
              }}
              disabled={!book.hardcoverId || hasActiveRequest}
            >
              Request
            </Button>
          </div>
        )}
      </div>
      {book.hardcoverId && showRequestButton && (
        <RequestDialog book={book} open={requestOpen} onOpenChange={setRequestOpen} />
      )}
    </>
  );
}
