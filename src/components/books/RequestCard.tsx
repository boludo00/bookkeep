import { Link } from 'react-router-dom';
import { User } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { BookRequest } from '@/types/book';

interface RequestCardProps {
  request: BookRequest;
}

const statusConfig = {
  requested: { label: 'Requested', className: 'status-requested' },
  approved: { label: 'Approved', className: 'status-approved' },
  processing: { label: 'Processing', className: 'status-approved' },
  available: { label: 'Available', className: 'status-available' },
  denied: { label: 'Denied', className: 'status-denied' },
  not_found: { label: 'Not Found', className: 'status-not-found' },
};

export function RequestCard({ request }: RequestCardProps) {
  const status = statusConfig[request.status];
  const year = new Date(request.book.publishedDate).getFullYear();
  const bookIdentifier =
    request.book.hardcoverId || request.book.hardcoverSlug || request.bookId;

  return (
    <Link
      to={`/book/${bookIdentifier}`}
      className="group relative flex overflow-hidden rounded-xl bg-card border border-border card-hover"
    >
      {/* Background Blur */}
      <div className="absolute inset-0 overflow-hidden">
        <img
          src={request.book.cover}
          alt=""
          className="h-full w-full object-cover opacity-20 blur-xl scale-110"
        />
        <div className="absolute inset-0 bg-card/80" />
      </div>

      {/* Content */}
      <div className="relative flex w-full p-4 gap-3 sm:gap-4">
        {/* Cover */}
        <div className="flex-shrink-0">
          <img
            src={request.book.cover}
            alt={request.book.title}
            className="h-24 w-16 sm:h-28 sm:w-20 rounded-lg object-cover shadow-lg"
          />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 flex flex-col gap-2">
          {/* Title and Year */}
          <div className="space-y-0.5">
            <span className="text-xs sm:text-sm text-muted-foreground">{year}</span>
            <h3 className="font-semibold text-foreground text-sm sm:text-base line-clamp-2">
              {request.book.title}
            </h3>
          </div>

          {/* User Info */}
          <div className="flex items-center gap-1.5 text-xs sm:text-sm text-muted-foreground">
            <User className="h-3 w-3 sm:h-4 sm:w-4 flex-shrink-0" />
            <span className="truncate">{request.userName}</span>
          </div>

          {/* Status Badge - with proper spacing */}
          <div className="flex items-center gap-2 mt-auto pt-1">
            <span className="text-xs text-muted-foreground flex-shrink-0">Status:</span>
            <Badge
              variant="outline"
              className={cn('text-xs border', status.className)}
            >
              {status.label}
            </Badge>
          </div>
        </div>
      </div>
    </Link>
  );
}
