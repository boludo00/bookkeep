import { useState, useEffect } from 'react';
import { BookOpen, Headphones, CheckCircle, Clock, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { requestsApi, booksApi } from '@/lib/api';
import type { Book } from '@/types/book';

interface RequestDialogProps {
  book: Book;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preferredFormat?: FormatSelection;
  disableFormats?: { ebook?: boolean; audiobook?: boolean };
}

type FormatSelection = 'ebook' | 'audiobook' | 'both';

const formatInfo = {
  ebook: { label: 'eBook', icon: BookOpen, description: 'Digital reading format' },
  audiobook: { label: 'Audiobook', icon: Headphones, description: 'Audio narration' },
} as const;

function getStatusBadge(status: string | null) {
  if (!status) return null;
  
  const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline'; icon?: typeof CheckCircle; className?: string }> = {
    requested: { label: 'Pending', variant: 'secondary', icon: Clock },
    approved: { label: 'Approved', variant: 'default', icon: Clock },
    processing: { label: 'Processing', variant: 'default', icon: Clock },
    available: { label: 'Available', variant: 'outline', icon: CheckCircle },
    not_found: { label: 'Not Found', variant: 'outline', className: 'border-destructive/40 text-destructive' },
  };
  
  const config = statusConfig[status] || { label: status, variant: 'secondary' as const };
  const Icon = config.icon;
  
  return (
    <Badge variant={config.variant} className={cn('text-xs', config.className)}>
      {Icon && <Icon className="h-3 w-3 mr-1" />}
      {config.label}
    </Badge>
  );
}

export function RequestDialog({
  book,
  open,
  onOpenChange,
  preferredFormat,
  disableFormats,
}: RequestDialogProps) {
  const [selectedFormat, setSelectedFormat] = useState<FormatSelection | null>(null);
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryClient = useQueryClient();

  // Fetch existing requests for this book
  const { data: existingRequests, isLoading: isLoadingRequests } = useQuery({
    queryKey: ['book-requests', book.hardcoverId],
    queryFn: () => book.hardcoverId ? requestsApi.getByHardcoverId(book.hardcoverId) : Promise.resolve({ ebook: null, audiobook: null, book_id: null }),
    enabled: open && !!book.hardcoverId,
  });

  // Determine which formats are available to request
  const ebookAlreadyRequested = !!existingRequests?.ebook && existingRequests?.ebook !== 'not_found';
  const audiobookAlreadyRequested = !!existingRequests?.audiobook && existingRequests?.audiobook !== 'not_found';

  const canRequestEbook = !ebookAlreadyRequested && !disableFormats?.ebook;
  const canRequestAudiobook = !audiobookAlreadyRequested && !disableFormats?.audiobook;
  const canRequestBoth = canRequestEbook && canRequestAudiobook;

  // Auto-select the only available format
  useEffect(() => {
    if (!isLoadingRequests) {
      if (preferredFormat === 'ebook' && canRequestEbook) {
        setSelectedFormat('ebook');
      } else if (preferredFormat === 'audiobook' && canRequestAudiobook) {
        setSelectedFormat('audiobook');
      } else if (canRequestEbook && !canRequestAudiobook) {
        setSelectedFormat('ebook');
      } else if (canRequestAudiobook && !canRequestEbook) {
        setSelectedFormat('audiobook');
      } else if (canRequestBoth) {
        setSelectedFormat('ebook'); // Default to ebook when both are available
      } else {
        setSelectedFormat(null);
      }
    }
  }, [canRequestEbook, canRequestAudiobook, canRequestBoth, isLoadingRequests, preferredFormat]);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setNotes('');
    }
  }, [open]);

  // First, ensure the book exists in our database
  const ensureBookMutation = useMutation({
    mutationFn: async () => {
      // Try to find book by hardcover_id or create it
      if (book.hardcoverId) {
        try {
          // Check if book exists
          const existingBooks = await booksApi.getAll(0, 1000);
          const existing = existingBooks.find((b: any) => 
            b.hardcover_id === book.hardcoverId || b.isbn === book.isbn
          );
          
          if (existing) {
            return existing.id;
          }
        } catch (e) {
          // Continue to create if lookup fails
        }
      }

      // Create book in database
      const newBook = await booksApi.create({
        title: book.title,
        author: book.author,
        isbn: book.isbn,
        description: book.description,
        cover_url: book.cover,
        published_date: book.publishedDate,
        rating: book.rating,
        page_count: book.pageCount,
        hardcover_id: book.hardcoverId,
        series: book.series,
        series_position: book.seriesPosition,
        genres: book.genres || [],
      });
      
      return newBook.id;
    },
  });

  const createRequestMutation = useMutation({
    mutationFn: async ({ bookId, format }: { bookId: number; format: string }) => {
      return requestsApi.create({
        book_id: bookId,
        format: format,
        notes: notes || undefined,
      });
    },
  });

  const handleSubmit = async () => {
    if (!selectedFormat) return;

    const formatLabel = selectedFormat === 'both' ? 'eBook and Audiobook' : formatInfo[selectedFormat].label;
    setIsSubmitting(true);

    try {
      // Ensure book exists in database
      const bookId = await ensureBookMutation.mutateAsync();

      // Create request(s) based on selection
      const formatsToRequest = selectedFormat === 'both'
        ? ['ebook', 'audiobook']
        : [selectedFormat];

      for (const format of formatsToRequest) {
        await createRequestMutation.mutateAsync({ bookId, format });
      }

      // Invalidate queries to trigger re-fetch
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      queryClient.invalidateQueries({ queryKey: ['book-requests', book.hardcoverId] });
      queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });

      toast.success('Request submitted!', {
        description: `Your ${formatLabel} request for "${book.title}" has been submitted.`,
      });

      setNotes('');
      onOpenChange(false);
    } catch (error: any) {
      console.error('Request submission error:', error);
      toast.error('Request failed', {
        description: error?.message || 'Failed to submit request. Please try again.',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const isLoading = isLoadingRequests;
  const noFormatsAvailable = !canRequestEbook && !canRequestAudiobook;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-foreground">Request Book</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Request "{book.title}" by {book.author}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : noFormatsAvailable ? (
          <div className="py-6 text-center space-y-4">
            <p className="text-muted-foreground">
              All available formats have already been requested for this book.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {existingRequests?.ebook && (
                <div className="flex items-center gap-2 text-sm">
                  <BookOpen className="h-4 w-4" />
                  <span>eBook:</span>
                  {getStatusBadge(existingRequests.ebook)}
                </div>
              )}
              {existingRequests?.audiobook && (
                <div className="flex items-center gap-2 text-sm">
                  <Headphones className="h-4 w-4" />
                  <span>Audiobook:</span>
                  {getStatusBadge(existingRequests.audiobook)}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Format Selection */}
            <div className="space-y-3">
              <Label className="text-foreground">Select Format</Label>
              <div className={cn("grid gap-3", canRequestBoth ? "grid-cols-3" : "grid-cols-2")}>
                {/* eBook option */}
                <button
                  type="button"
                  disabled={!canRequestEbook}
                  onClick={() => canRequestEbook && setSelectedFormat('ebook')}
                  className={cn(
                    'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all relative',
                    !canRequestEbook && 'opacity-50 cursor-not-allowed',
                    selectedFormat === 'ebook'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-secondary/50 text-muted-foreground hover:border-muted-foreground'
                  )}
                >
                  <BookOpen className="h-6 w-6" />
                  <span className="text-sm font-medium">eBook</span>
                  {ebookAlreadyRequested && (
                    <div className="absolute -top-2 -right-2">
                      {getStatusBadge(existingRequests?.ebook ?? null)}
                    </div>
                  )}
                </button>

                {/* Audiobook option */}
                <button
                  type="button"
                  disabled={!canRequestAudiobook}
                  onClick={() => canRequestAudiobook && setSelectedFormat('audiobook')}
                  className={cn(
                    'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all relative',
                    !canRequestAudiobook && 'opacity-50 cursor-not-allowed',
                    selectedFormat === 'audiobook'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-secondary/50 text-muted-foreground hover:border-muted-foreground'
                  )}
                >
                  <Headphones className="h-6 w-6" />
                  <span className="text-sm font-medium">Audiobook</span>
                  {audiobookAlreadyRequested && (
                    <div className="absolute -top-2 -right-2">
                      {getStatusBadge(existingRequests?.audiobook ?? null)}
                    </div>
                  )}
                </button>

                {/* Both option - only show when both are available */}
                {canRequestBoth && (
                  <button
                    type="button"
                    onClick={() => setSelectedFormat('both')}
                    className={cn(
                      'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all',
                      selectedFormat === 'both'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-secondary/50 text-muted-foreground hover:border-muted-foreground'
                    )}
                  >
                    <div className="flex gap-1">
                      <BookOpen className="h-5 w-5" />
                      <Headphones className="h-5 w-5" />
                    </div>
                    <span className="text-sm font-medium">Both</span>
                  </button>
                )}
              </div>
            </div>

            {/* Notes */}
            <div className="space-y-3">
              <Label htmlFor="notes" className="text-foreground">
                Notes (optional)
              </Label>
              <Textarea
                id="notes"
                placeholder="Any special requests or notes..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="bg-secondary border-border resize-none"
                rows={3}
              />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="border-border"
            disabled={isSubmitting}
          >
            {noFormatsAvailable ? 'Close' : 'Cancel'}
          </Button>
          {!noFormatsAvailable && !isLoading && (
            <Button
              onClick={handleSubmit}
              disabled={!selectedFormat || isSubmitting}
              className="bg-primary hover:bg-primary/90"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Submitting...
                </>
              ) : (
                'Submit Request'
              )}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
