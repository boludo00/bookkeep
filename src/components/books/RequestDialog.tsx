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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { requestsApi, booksApi, readarrApi, hardcoverApi } from '@/lib/api';
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
  const [selectedEditionIds, setSelectedEditionIds] = useState<{ ebook?: number; audiobook?: number }>({});
  const [errorDialogOpen, setErrorDialogOpen] = useState(false);
  const [errorSummary, setErrorSummary] = useState('');
  const [errorDetails, setErrorDetails] = useState('');
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditionError, setIsEditionError] = useState(false);
  const queryClient = useQueryClient();

  // Fetch configured formats
  const { data: configuredFormats, isLoading: isLoadingFormats } = useQuery({
    queryKey: ['configured-formats'],
    queryFn: () => readarrApi.getConfiguredFormats(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Fetch existing requests for this book
  const { data: existingRequests, isLoading: isLoadingRequests } = useQuery({
    queryKey: ['book-requests', book.hardcoverId],
    queryFn: () => book.hardcoverId ? requestsApi.getByHardcoverId(book.hardcoverId) : Promise.resolve({ ebook: null, audiobook: null, book_id: null }),
    enabled: open && !!book.hardcoverId,
  });

  // Determine which formats are available to request
  const ebookConfigured = configuredFormats?.ebook ?? false;
  const audiobookConfigured = configuredFormats?.audiobook ?? false;
  const ebookAlreadyRequested = !!existingRequests?.ebook && existingRequests?.ebook !== 'not_found';
  const audiobookAlreadyRequested = !!existingRequests?.audiobook && existingRequests?.audiobook !== 'not_found';
  
  const canRequestEbook = ebookConfigured && !ebookAlreadyRequested && !disableFormats?.ebook;
  const canRequestAudiobook = audiobookConfigured && !audiobookAlreadyRequested && !disableFormats?.audiobook;
  const canRequestBoth = canRequestEbook && canRequestAudiobook;

  const { data: ebookEditions, isLoading: isLoadingEbookEditions } = useQuery({
    queryKey: ['hardcover-editions', book.hardcoverId, 'ebook'],
    queryFn: () => hardcoverApi.getEditions(book.hardcoverId as number, 'ebook'),
    enabled: open && !!book.hardcoverId && canRequestEbook,
    staleTime: 10 * 60 * 1000,
  });

  const { data: audiobookEditions, isLoading: isLoadingAudiobookEditions } = useQuery({
    queryKey: ['hardcover-editions', book.hardcoverId, 'audiobook'],
    queryFn: () => hardcoverApi.getEditions(book.hardcoverId as number, 'audiobook'),
    enabled: open && !!book.hardcoverId && canRequestAudiobook,
    staleTime: 10 * 60 * 1000,
  });

  // Auto-select the only available format
  useEffect(() => {
    if (!isLoadingFormats && !isLoadingRequests) {
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
  }, [canRequestEbook, canRequestAudiobook, canRequestBoth, isLoadingFormats, isLoadingRequests]);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setNotes('');
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      setSelectedEditionIds({});
    }
  }, [open]);

  useEffect(() => {
    if (!ebookEditions?.editions?.length) return;
    if (selectedEditionIds.ebook) return;
    const defaultId = ebookEditions.default_cover_edition_id;
    const match = defaultId
      ? ebookEditions.editions.find((edition) => edition.id === defaultId)
      : undefined;
    setSelectedEditionIds((prev) => ({
      ...prev,
      ebook: match?.id ?? ebookEditions.editions[0]?.id,
    }));
  }, [ebookEditions, selectedEditionIds.ebook]);

  useEffect(() => {
    if (!audiobookEditions?.editions?.length) return;
    if (selectedEditionIds.audiobook) return;
    setSelectedEditionIds((prev) => ({
      ...prev,
      audiobook: audiobookEditions.editions[0]?.id,
    }));
  }, [audiobookEditions, selectedEditionIds.audiobook]);

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
    mutationFn: async ({ bookId, format, editionId }: { bookId: number; format: string; editionId?: number }) => {
      return requestsApi.create({
        book_id: bookId,
        format: format,
        edition_id: editionId,
        notes: notes || undefined,
      });
    },
  });

  const handleSubmit = () => {
    if (!selectedFormat) return;
    
    const formatLabel = selectedFormat === 'both' ? 'eBook and Audiobook' : formatInfo[selectedFormat].label;
    const currentNotes = notes;
    const currentFormat = selectedFormat;
    const toastId = `request-${book.hardcoverId}-${currentFormat}`;
    setIsSubmitting(true);
    
    // Show pending toast
    toast.loading(`Submitting ${formatLabel} request...`, {
      id: toastId,
    });
    
    // Process in background
    (async () => {
      try {
        // Ensure book exists in database
        const bookId = await ensureBookMutation.mutateAsync();
        
        // Create request(s) based on selection
        const formatsToRequest = currentFormat === 'both' 
          ? ['ebook', 'audiobook'] 
          : [currentFormat];
        
        const requestResults = [];
        for (const format of formatsToRequest) {
          const editionId = selectedEditionIds[format as 'ebook' | 'audiobook'];
          const result = await createRequestMutation.mutateAsync({ bookId, format, editionId });
          requestResults.push({ format, result });
        }
        
        // Invalidate queries to trigger re-fetch and start polling
        queryClient.invalidateQueries({ queryKey: ['requests'] });
        queryClient.invalidateQueries({ queryKey: ['book-requests', book.hardcoverId] });
        queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });
        queryClient.invalidateQueries({ queryKey: ['readarr', 'availability'] });
        
        const confirmations = requestResults.map(({ format, result }: any) => {
          const label = format === 'ebook' ? 'eBook' : 'Audiobook';
          if (!result?.readarrReceived) {
            return `${label}: request created (Readarr not confirmed)`;
          }
          if (result?.readarrSearchTriggered === true) {
            return `${label}: Readarr accepted + search triggered`;
          }
          if (result?.readarrSearchTriggered === false) {
            const status = result?.readarrSearchStatusCode ? ` (status ${result.readarrSearchStatusCode})` : '';
            return `${label}: Readarr accepted, search not confirmed${status}`;
          }
          return `${label}: Readarr accepted`;
        });

        const hasReadarrFailure = requestResults.some(({ result }: any) => result?.readarrReceived === false);
        const toastFn = hasReadarrFailure ? toast.warning : toast.success;
        toastFn('Request submitted!', {
          id: toastId,
          description: confirmations.length > 0
            ? confirmations.join(' • ')
            : `Your ${formatLabel} request for "${book.title}" has been sent.`,
        });
        setNotes('');
        onOpenChange(false);
      } catch (error: any) {
        console.error('Request submission error:', error);
        toast.dismiss(toastId);
        const rawMessage = error?.message || 'Please try again.';
        const marker = 'Failed to add to Readarr:';
        const detail = rawMessage.includes(marker)
          ? rawMessage.split(marker)[1].trim()
          : rawMessage;

        // Check if this is an edition selection error
        const isEditionIssue = rawMessage.includes('Sequence contains no matching element') ||
                                rawMessage.includes('no matching element') ||
                                rawMessage.includes('edition');

        setIsEditionError(isEditionIssue);
        setErrorSummary(detail || 'Readarr rejected the request.');
        setErrorDetails(rawMessage);
        setShowErrorDetails(false);
        setErrorDialogOpen(true);
      } finally {
        setIsSubmitting(false);
      }
    })();
  };

  const isLoading = isLoadingFormats || isLoadingRequests || isLoadingEbookEditions || isLoadingAudiobookEditions;
  const noFormatsAvailable = !canRequestEbook && !canRequestAudiobook;

  const formatAudioDuration = (seconds?: number | null) => {
    if (!seconds) return null;
    const mins = Math.round(seconds / 60);
    if (mins < 60) return `${mins} min`;
    const hours = Math.floor(mins / 60);
    const remaining = mins % 60;
    return `${hours}h ${remaining}m`;
  };

  const renderEditionPicker = (
    format: 'ebook' | 'audiobook',
    editionsData?: {
      editions: Array<any>;
    }
  ) => {
    if (!editionsData?.editions?.length) {
      return (
        <div className="text-sm text-muted-foreground">
          No editions found for this format.
        </div>
      );
    }

    const selectedId = selectedEditionIds[format];
    const selectedEdition = editionsData.editions.find((edition) => edition.id === selectedId);

    return (
      <div className="space-y-3">
        <Label className="text-foreground">
          {format === 'ebook' ? 'eBook Edition' : 'Audiobook Edition'}
        </Label>
        <Select
          value={selectedId ? String(selectedId) : undefined}
          onValueChange={(value) =>
            setSelectedEditionIds((prev) => ({
              ...prev,
              [format]: Number(value),
            }))
          }
        >
          <SelectTrigger className="bg-secondary border-border">
            <SelectValue placeholder="Select an edition" />
          </SelectTrigger>
          <SelectContent>
            {editionsData.editions.map((edition) => {
              const language = edition.language || edition.language_code2 || 'Unknown';
              const publisher = edition.publisher || 'Unknown';
              const lengthOrPages =
                format === 'audiobook'
                  ? formatAudioDuration(edition.audio_seconds) || 'Unknown'
                  : edition.pages || 'Unknown';
              const score = edition.score ?? 'N/A';
              return (
                <SelectItem key={edition.id} value={String(edition.id)}>
                  {`${edition.title || `Edition ${edition.id}`} • ${language} • ${publisher} • ${
                    format === 'audiobook' ? 'Length' : 'Pages'
                  }: ${lengthOrPages} • Score: ${score}`}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        {selectedEdition && (
          <div className="rounded-md border border-border bg-secondary/40 p-3 text-sm text-muted-foreground">
            <div className="flex flex-wrap gap-4">
              <span>
                <span className="text-foreground">Language:</span>{' '}
                {selectedEdition.language || selectedEdition.language_code2 || 'Unknown'}
              </span>
              <span>
                <span className="text-foreground">Publisher:</span>{' '}
                {selectedEdition.publisher || 'Unknown'}
              </span>
              <span>
                <span className="text-foreground">
                  {format === 'audiobook' ? 'Length:' : 'Pages:'}
                </span>{' '}
                {format === 'audiobook'
                  ? formatAudioDuration(selectedEdition.audio_seconds) || 'Unknown'
                  : selectedEdition.pages || 'Unknown'}
              </span>
              <span>
                <span className="text-foreground">Score:</span>{' '}
                {selectedEdition.score ?? 'N/A'}
              </span>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
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
              {!ebookConfigured && !audiobookConfigured 
                ? "No Readarr servers are configured. Please ask an administrator to set up a server."
                : "All available formats have already been requested for this book."}
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
                  {!ebookConfigured && (
                    <span className="text-xs text-muted-foreground">Not configured</span>
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
                  {!audiobookConfigured && (
                    <span className="text-xs text-muted-foreground">Not configured</span>
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

            {/* Edition Selection */}
            {selectedFormat === 'ebook' && renderEditionPicker('ebook', ebookEditions)}
            {selectedFormat === 'audiobook' && renderEditionPicker('audiobook', audiobookEditions)}
            {selectedFormat === 'both' && (
              <div className="space-y-4">
                {renderEditionPicker('ebook', ebookEditions)}
                {renderEditionPicker('audiobook', audiobookEditions)}
              </div>
            )}

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

      <Dialog open={errorDialogOpen} onOpenChange={(open) => {
        setErrorDialogOpen(open);
        if (!open) {
          // Reset edition error state when dialog closes
          setIsEditionError(false);
        }
      }}>
        <DialogContent className="sm:max-w-md bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Request Failed</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <span className="font-medium">Failed to add to Readarr.</span>{' '}
              <span className="text-destructive/80">{errorSummary}</span>
            </div>

            {isEditionError && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
                <p className="font-medium text-amber-400 mb-2">Edition Selection Issue</p>
                <p className="text-amber-400/80 text-xs">
                  Readarr couldn't find the selected edition. Try one of these solutions:
                </p>
                <ul className="mt-2 space-y-1 text-xs text-amber-400/80 list-disc list-inside">
                  <li>Select a different edition from the dropdown above</li>
                  <li>Choose an edition with a higher "Score" value</li>
                  <li>Try selecting an edition from a different publisher</li>
                </ul>
              </div>
            )}

            <div className="flex gap-2">
              <Button
                type="button"
                variant="ghost"
                className="px-2 text-sm text-muted-foreground hover:text-foreground"
                onClick={() => setShowErrorDetails((value) => !value)}
              >
                {showErrorDetails ? 'Hide Logs' : 'Show Logs'}
              </Button>
              {isEditionError && (
                <Button
                  type="button"
                  variant="outline"
                  className="px-3 text-sm"
                  onClick={() => setErrorDialogOpen(false)}
                >
                  Try Different Edition
                </Button>
              )}
            </div>

            {showErrorDetails && (
              <pre className="max-h-56 overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                {errorDetails}
              </pre>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
