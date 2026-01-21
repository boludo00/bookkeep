import { useState } from 'react';
import { Clock, CheckCircle, XCircle, Loader2, Trash2, User, CheckCircle2, Library } from 'lucide-react';
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
  requested: { label: 'Requested', className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50', icon: Clock },
  approved: { label: 'Approved', className: 'bg-blue-500/20 text-blue-400 border-blue-500/50', icon: CheckCircle },
  processing: { label: 'Processing', className: 'bg-blue-500/20 text-blue-400 border-blue-500/50', icon: Loader2 },
  available: { label: 'Available', className: 'bg-green-500/20 text-green-400 border-green-500/50', icon: CheckCircle },
  denied: { label: 'Denied', className: 'bg-red-500/20 text-red-400 border-red-500/50', icon: XCircle },
  not_found: { label: 'Not Found', className: 'bg-red-500/20 text-red-400 border-red-500/50', icon: XCircle },
  pending: { label: 'Pending', className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50', icon: Clock },
};

function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return 'recently';
  
  const date = new Date(dateString);
  // Check if date is valid
  if (isNaN(date.getTime())) return 'recently';
  
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  // Handle negative or huge values (bad data)
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

function RequestRow({ request }: { request: BookRequest }) {
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
    // Try numeric hardcoverId first, then fall back to slug
    const bookIdentifier = request.book.hardcoverId || request.book.hardcoverSlug;
    if (bookIdentifier) {
      window.location.href = `/book/${bookIdentifier}`;
    } else {
      toast.error('Book ID not available');
    }
  };

  return (
    <div className="relative group overflow-hidden rounded-lg bg-card border border-border hover:border-muted transition-all">
      {/* Background Image */}
      <div 
        className="absolute inset-0 opacity-10 group-hover:opacity-15 transition-opacity"
        style={{
          backgroundImage: `url(${request.book.cover})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
        }}
      />
      
      <div className="relative flex gap-6 p-6">
        {/* Left: Thumbnail and Info */}
        <div className="flex-shrink-0">
          <div 
            className="w-24 h-32 rounded-lg overflow-hidden cursor-pointer shadow-lg"
            onClick={handleBookClick}
          >
            <img
              src={request.book.cover}
              alt={request.book.title}
              className="w-full h-full object-cover"
            />
          </div>
          {request.book.publishedDate && (
            <p className="text-xs text-muted-foreground mt-2 text-center">
              {new Date(request.book.publishedDate).getFullYear()}
            </p>
          )}
        </div>

        {/* Middle: Title and Author */}
        <div className="flex-1 min-w-0">
          <h3 
            className="text-xl font-bold text-foreground mb-1 cursor-pointer hover:text-primary transition-colors"
            onClick={handleBookClick}
          >
            {request.book.title}
          </h3>
          <p className="text-sm text-muted-foreground mb-4">{request.book.author}</p>
          
          {/* Format Badge */}
          <Badge variant="outline" className="text-xs capitalize border-border mb-4">
            {request.format}
          </Badge>
        </div>

        {/* Right: Status and Actions */}
        <div className="flex-shrink-0 w-64 space-y-4">
          {/* Status */}
          <div>
            <p className="text-xs text-muted-foreground mb-2">Status</p>
            <Badge
              variant="outline"
              className={cn(
                'flex items-center gap-2 w-fit px-3 py-1',
                status.className
              )}
            >
              <StatusIcon className={cn('h-3 w-3', isProcessing && 'animate-spin')} />
              {status.label}
            </Badge>
          </div>

          {/* Requested By / Import Source */}
          <div>
            {request.source === 'booklore_import' ? (
              <>
                <p className="text-xs text-muted-foreground mb-2">
                  Imported {formatRelativeTime(request.createdAt)}
                </p>
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-emerald-500/20 flex items-center justify-center">
                    <Library className="h-4 w-4 text-emerald-400" />
                  </div>
                  <span className="text-sm text-emerald-400 font-medium">From Booklore</span>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-2">
                  Requested {formatRelativeTime(request.createdAt)} by
                </p>
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium text-primary">
                    {getUserInitials(request.userName)}
                  </div>
                  <span className="text-sm text-foreground">{request.userName}</span>
                </div>
              </>
            )}
          </div>

          {/* Modified By - only show if actually modified */}
          {request.updatedAt && request.updatedAt !== request.createdAt && request.source !== 'booklore_import' && (
            <div>
              <p className="text-xs text-muted-foreground mb-2">
                Modified {formatRelativeTime(request.updatedAt)}
              </p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-col gap-2 pt-2">
            {isProcessing && (
              <Button
                variant="default"
                size="sm"
                onClick={() => markAvailableMutation.mutate()}
                disabled={markAvailableMutation.isPending}
                className="w-full bg-green-600 hover:bg-green-700 text-white"
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Mark as Available
              </Button>
            )}

            <Button
              variant="destructive"
              size="sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="w-full"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Request
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
    ? 'requested' 
    : activeTab === 'approved'
    ? undefined // We'll filter client-side for approved/processing
    : activeTab;

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['requests', statusFilter],
    queryFn: () => requestsApi.getAll(0, 100, statusFilter),
    refetchInterval: (query) => {
      // Auto-refresh every 10 seconds if there are any processing requests
      const data = query.state.data;
      const hasProcessing = Array.isArray(data) && data.some((req: any) => req.status === 'processing');
      return hasProcessing ? 10000 : false;
    },
  });

  // Transform API requests to match frontend BookRequest type
  // Filter out requests without books to prevent UI issues
  const transformedRequests: BookRequest[] = requests
    .filter((req: any) => req.book) // Only include requests with associated books
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
    if (status === 'pending') return transformedRequests.filter((r) => r.status === 'requested');
    if (status === 'approved') return transformedRequests.filter((r) => ['approved', 'processing'].includes(r.status));
    if (status === 'available') return transformedRequests.filter((r) => r.status === 'available');
    return transformedRequests;
  };

  const filteredRequests = filterRequests(activeTab);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
          Requests
        </h1>
        <p className="text-muted-foreground mt-2">
          Track the status of your book requests
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="available">Available</TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-6">
          {isLoading ? (
            <div className="text-center py-12">
              <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground mb-4" />
              <div className="text-muted-foreground">Loading requests...</div>
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="text-center py-12">
              <Clock className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium text-foreground">No requests found</h3>
              <p className="text-muted-foreground mt-1">
                Start browsing and request some books!
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredRequests.map((request) => (
                <RequestRow key={request.id} request={request} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
