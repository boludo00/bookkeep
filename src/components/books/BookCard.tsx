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
  const hasActiveRequest = requestStatuses.some(
    (value) => value !== 'not_found' && value !== 'available'
  );
  const effectiveStatus = status !== 'none' ? status : hasActiveRequest ? 'requested' : 'none';
  const bookLink = book.seriesId
    ? `/book/${book.id}?seriesId=${book.seriesId}`
    : `/book/${book.id}`;

  return (
    <>
      <div className="group relative">
        <Link to={bookLink} className="block">
          {/* Book cover with cinematic effects */}
          <div className="book-cover-glow">
            <div className="book-cover aspect-[2/3] bg-card overflow-hidden">
              <img
                src={book.cover}
                alt={book.title}
                className="h-full w-full object-cover transition-all duration-500 group-hover:scale-105"
                loading="lazy"
              />

              {/* Gradient overlays */}
              <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

              {/* Top vignette for badges */}
              <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-background/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

              {/* Format availability badges */}
              {isAnyFormatAvailable && (
                <div className="absolute top-2.5 right-2.5 flex gap-1.5">
                  {ebookAvailable && (
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/90 text-white shadow-lg shadow-emerald-500/30 backdrop-blur-sm"
                      title="eBook Available"
                    >
                      <BookOpen className="h-3.5 w-3.5" />
                    </div>
                  )}
                  {audiobookAvailable && (
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/90 text-white shadow-lg shadow-violet-500/30 backdrop-blur-sm"
                      title="Audiobook Available"
                    >
                      <Headphones className="h-3.5 w-3.5" />
                    </div>
                  )}
                </div>
              )}

              {/* Requested badge */}
              {!isAnyFormatAvailable && effectiveStatus === 'requested' && (
                <div className="absolute top-2.5 right-2.5">
                  <div
                    className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/90 text-amber-foreground shadow-lg shadow-amber-500/30 backdrop-blur-sm"
                    title="Requested"
                  >
                    <Clock className="h-3.5 w-3.5" />
                  </div>
                </div>
              )}

              {/* Genre badge */}
              {book.genres[0] && (
                <div className="absolute top-2.5 left-2.5">
                  <span className="inline-flex items-center rounded-md bg-primary/90 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground shadow-lg shadow-primary/20 backdrop-blur-sm">
                    {book.genres[0]}
                  </span>
                </div>
              )}

              {/* Hover info panel */}
              <div className="absolute bottom-0 left-0 right-0 p-4 translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-300">
                <h3 className="font-semibold text-foreground line-clamp-2 text-sm leading-snug">
                  {book.title}
                </h3>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                  {book.author}
                </p>
                {showRating && book.rating > 0 && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    <span className="text-xs font-medium text-foreground">
                      {formatRating(book.rating)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </Link>

        {/* Request button */}
        {!isAnyFormatAvailable && showRequestButton && (
          <div className="absolute bottom-3 right-3 translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-300">
            <Button
              size="sm"
              className="h-8 px-3 text-xs font-medium rounded-lg bg-primary/90 hover:bg-primary text-primary-foreground shadow-lg shadow-primary/30 backdrop-blur-sm"
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
