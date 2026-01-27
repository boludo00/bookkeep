import { useState } from 'react';
import { Clock, CheckCircle, XCircle, Loader2, Trash2, User, CheckCircle2, Library, Inbox } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { requestsApi } from '@/lib/api';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import type { BookRequest } from '@/types/book';

const statusConfig = {
  requested: { label: 'Requested', className: 'status-requested', icon: Clock },
  approved: { label: 'Approved', className: 'status-approved', icon: CheckCircle },
  processing: { label: 'Processing', className: 'status-processing', icon: Loader2 },
  available: { label: 'Available', className: 'status-available', icon: CheckCircle },
  denied: { label: 'Denied', className: 'status-denied', icon: XCircle },
  not_found: { label: 'Not Found', className: 'status-not-found', icon: XCircle },
  pending: { label: 'Pending', className: 'status-requested', icon: Clock },
};

function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return 'recently';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return 'recently';

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0 || diffDays > 3650) return 'recently';

  if (diffDays === 0) return 'today';
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
  return `${Math.floor(diffDays / 365)} years ago`;
}

function getUserInitials(name: string): string {
  if (!name) return '?';
  const parts = name.split(' ');
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.substring(0, 2).toUpperCase();
}

function RequestRow({ request, index }: { request: BookRequest; index: number }) {
  const queryClient = useQueryClient();
  const status = statusConfig[request.status] ?? statusConfig.requested;
  const StatusIcon = status.icon;
  const isProcessing = request.status === 'processing';

  const deleteMutation = useMutation({
    mutationFn: () => requestsApi.delete(Number(request.id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      toast.success('Request deleted');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete request', {
        description: error.message,
      });
    },
  });

  const markAvailableMutation = useMutation({
    mutationFn: () => requestsApi.update(Number(request.id), { status: 'available' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      toast.success('Request marked as available');
    },
    onError: (error: Error) => {
      toast.error('Failed to mark request as available', {
        description: error.message,
      });
    },
  });

  const handleBookClick = () => {
    const bookIdentifier = request.book.hardcoverId || request.book.hardcoverSlug;
    if (bookIdentifier) {
      window.location.href = `/book/${bookIdentifier}`;
    } else {
      toast.error('Book ID not available');
    }
  };

  return (
    <div
      className="group relative overflow-hidden rounded-2xl bg-card border border-border/50 hover:border-primary/30 transition-[border-color] duration-300 animate-fade-in-up"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Subtle background image (hidden on mobile for performance) */}
      <div
        className="absolute inset-0 opacity-[0.03] group-hover:opacity-[0.06] transition-opacity duration-500 hidden md:block"
        style={{
          backgroundImage: `url(${request.book.cover})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          filter: 'blur(20px)',
        }}
      />

      <div className="relative flex flex-col md:flex-row gap-6 p-6">
        {/* Book cover */}
        <div className="flex-shrink-0 mx-auto md:mx-0">
          <div
            className="book-cover w-28 h-40 cursor-pointer group/cover"
            onClick={handleBookClick}
          >
            <img
              src={request.book.cover}
              alt={request.book.title}
              loading="lazy"
              className="w-full h-full object-cover transition-transform duration-300 group-hover/cover:scale-105"
            />
          </div>
          {request.book.publishedDate && (
            <p className="text-xs text-muted-foreground/60 mt-2 text-center font-medium">
              {new Date(request.book.publishedDate).getFullYear()}
            </p>
          )}
        </div>

        {/* Book info */}
        <div className="flex-1 min-w-0 text-center md:text-left">
          <h3
            className="text-xl font-bold text-foreground mb-1.5 cursor-pointer hover:text-primary transition-colors duration-300 line-clamp-2"
            onClick={handleBookClick}
          >
            {request.book.title}
          </h3>
          <p className="text-sm text-muted-foreground mb-4">{request.book.author}</p>

          {/* Format badge */}
          <Badge variant="outline" className="text-xs capitalize border-border/50 bg-muted/30 mb-4">
            {request.format}
          </Badge>
        </div>

        {/* Status and actions */}
        <div className="flex-shrink-0 w-full md:w-64 space-y-4">
          {/* Status badge */}
          <div>
            <p className="text-xs text-muted-foreground/60 mb-2 uppercase tracking-wider font-medium">Status</p>
            <Badge
              variant="outline"
              className={cn(
                'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border',
                status.className
              )}
            >
              <StatusIcon className={cn('h-3.5 w-3.5', isProcessing && 'animate-spin')} />
              {status.label}
            </Badge>
          </div>

          {/* Requested by / Import source */}
          <div>
            {request.source === 'booklore_import' ? (
              <>
                <p className="text-xs text-muted-foreground/60 mb-2">
                  Imported {formatRelativeTime(request.createdAt)}
                </p>
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-emerald-500/15 flex items-center justify-center">
                    <Library className="h-4 w-4 text-emerald-400" />
                  </div>
                  <span className="text-sm text-emerald-400 font-medium">From Booklore</span>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground/60 mb-2">
                  Requested {formatRelativeTime(request.createdAt)}
                </p>
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-primary/15 flex items-center justify-center text-xs font-semibold text-primary">
                    {getUserInitials(request.userName)}
                  </div>
                  <span className="text-sm text-foreground font-medium">{request.userName}</span>
                </div>
              </>
            )}
          </div>

          {/* Modified date */}
          {request.updatedAt && request.updatedAt !== request.createdAt && request.source !== 'booklore_import' && (
            <p className="text-xs text-muted-foreground/60">
              Modified {formatRelativeTime(request.updatedAt)}
            </p>
          )}

          {/* Action buttons */}
          <div className="flex flex-col gap-2 pt-2">
            {isProcessing && (
              <Button
                size="sm"
                onClick={() => markAvailableMutation.mutate()}
                disabled={markAvailableMutation.isPending}
                className="w-full h-9 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20"
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Mark Available
              </Button>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="w-full h-9 rounded-lg border-rose-500/30 text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/50"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Requests() {
  const [activeTab, setActiveTab] = useState('all');

  const statusFilter = activeTab === 'all'
    ? undefined
    : activeTab === 'pending'
    ? 'pending'
    : activeTab === 'approved'
    ? undefined
    : activeTab;

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['requests', statusFilter],
    queryFn: () => requestsApi.getAll(0, 100, statusFilter),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasProcessing = Array.isArray(data) && data.some((req: any) => req.status === 'processing');
      return hasProcessing ? 10000 : false;
    },
  });

  const transformedRequests: BookRequest[] = requests
    .filter((req: any) => req.book)
    .map((req: any) => ({
      id: String(req.id),
      bookId: String(req.book?.hardcover_id || req.book_id),
      book: {
        id: String(req.book.id),
        title: req.book.title || 'Unknown Title',
        author: req.book.author || 'Unknown Author',
        cover: req.book.cover_url || '/placeholder.svg',
        description: req.book.description || '',
        publishedDate: req.book.published_date || '',
        genres: req.book.genres ? (typeof req.book.genres === 'string' ? req.book.genres.split(',') : req.book.genres) : [],
        rating: req.book.rating || 0,
        series: req.book.series,
        seriesPosition: req.book.series_position,
        hardcoverId: req.book.hardcover_id,
        hardcoverSlug: req.book.hardcover_slug,
        isbn: req.book.isbn,
        pageCount: req.book.page_count,
      },
      userId: String(req.user_id),
      userName: req.user?.username || req.user?.full_name || 'Unknown User',
      format: req.format,
      status: req.status,
      source: req.source || 'user_request',
      notes: req.notes,
      adminNotes: req.admin_notes,
      createdAt: req.created_at,
      updatedAt: req.updated_at,
    }));

  const filterRequests = (status: string) => {
    if (status === 'all') return transformedRequests;
    if (status === 'pending') return transformedRequests.filter((r) => r.status === 'pending');
    if (status === 'approved') return transformedRequests.filter((r) => ['approved', 'processing'].includes(r.status));
    if (status === 'available') return transformedRequests.filter((r) => r.status === 'available');
    return transformedRequests;
  };

  const filteredRequests = filterRequests(activeTab);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="relative">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
            <Clock className="h-5 w-5 text-primary" />
          </div>
          <span className="text-sm font-medium text-primary uppercase tracking-wider">Library</span>
        </div>
        <h1 className="text-4xl font-bold text-foreground tracking-tight">
          Requests
        </h1>
        <p className="mt-2 text-muted-foreground">
          Track the status of your book requests
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="h-12 p-1.5 bg-card/50 border border-border/50 rounded-xl">
          <TabsTrigger value="all" className="h-9 px-4 rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            All
          </TabsTrigger>
          <TabsTrigger value="pending" className="h-9 px-4 rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            Pending
          </TabsTrigger>
          <TabsTrigger value="approved" className="h-9 px-4 rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            Approved
          </TabsTrigger>
          <TabsTrigger value="available" className="h-9 px-4 rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            Available
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-8">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16">
              <Loader2 className="h-10 w-10 animate-spin text-primary mb-4" />
              <p className="text-muted-foreground font-medium">Loading requests...</p>
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-muted/30 mb-6">
                <Inbox className="h-10 w-10 text-muted-foreground/50" />
              </div>
              <h3 className="text-xl font-semibold text-foreground mb-2">No requests found</h3>
              <p className="text-muted-foreground text-center max-w-sm">
                Start browsing the catalog and request some books to build your library.
              </p>
              <Button asChild className="mt-6 h-11 px-6 rounded-xl">
                <Link to="/">Discover Books</Link>
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredRequests.map((request, index) => (
                <RequestRow key={request.id} request={request} index={index} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
