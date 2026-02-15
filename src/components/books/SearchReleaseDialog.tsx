import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Download, Search, HardDrive, Wifi, BookOpen, Headphones, CheckCircle, RefreshCw, XCircle, ExternalLink, Globe } from 'lucide-react';
import { DirectDownloadProgress } from '@/components/books/DirectDownloadProgress';
import { Progress } from '@/components/ui/progress';
import { downloadsApi, ReleaseInfo, booksApi, directDownloadApi } from '@/lib/api';
import { toast } from 'sonner';

interface SearchReleaseDialogProps {
  book: {
    id?: number;
    hardcoverId?: number;
    title: string;
    author: string;
    isbn?: string;
    description?: string;
    cover?: string;
    publishedDate?: string;
    rating?: number;
    pageCount?: number;
    series?: string;
    seriesPosition?: number;
    genres?: string[];
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
  formatType?: 'ebook' | 'audiobook'; // Optional - defaults to 'ebook' tab
  sourceFilter?: 'prowlarr' | 'direct'; // Optional - filter by source
}

export function SearchReleaseDialog({
  book,
  open,
  onOpenChange,
  formatType = 'ebook',
  sourceFilter,
}: SearchReleaseDialogProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'ebook' | 'audiobook'>(formatType);

  // Track download states for each release URL
  // States: 'pending' (spinner only), 'downloading' (progress bar), 'complete' (badge)
  const [downloadStates, setDownloadStates] = useState<Map<string, string>>(new Map());
  const completedTasksRef = useRef<Set<number>>(new Set());

  // Update active tab when formatType prop changes
  useEffect(() => {
    if (open) {
      setActiveTab(formatType);
    }
  }, [open, formatType]);

  // Compute which tab should be active based on availability
  const getValidActiveTab = (): 'ebook' | 'audiobook' => {
    if (!dbBook) return activeTab;

    // If both formats are owned, doesn't matter (won't render tabs)
    if (dbBook.ebook_available && dbBook.audiobook_available) {
      return activeTab;
    }

    // If only ebook is owned, must use audiobook tab
    if (dbBook.ebook_available && !dbBook.audiobook_available) {
      return 'audiobook';
    }

    // If only audiobook is owned, must use ebook tab
    if (dbBook.audiobook_available && !dbBook.ebook_available) {
      return 'ebook';
    }

    // Both unavailable, use current activeTab
    return activeTab;
  };

  // Check if direct downloads are enabled
  const { data: directDownloadSettings } = useQuery({
    queryKey: ['direct-downloads', 'settings'],
    queryFn: () => directDownloadApi.getSettings(),
    staleTime: 5 * 60 * 1000,
  });
  const directDownloadsEnabled = directDownloadSettings?.enabled ?? false;

  // Ensure book exists in database
  const {
    data: bookId,
    isLoading: isEnsuring,
    error: ensureError,
  } = useQuery({
    queryKey: ['ensure-book', book.hardcoverId || book.title],
    queryFn: async () => {
      // If we already have a book ID, use it
      if (book.id) {
        return book.id;
      }

      // For books without an ID, just create them directly
      // Skip the slow getAll query that was causing hangs
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
    enabled: open,
    staleTime: Infinity, // Book ID won't change
  });

  // Fetch book details to check availability
  // Use a simpler approach - just assume both formats are NOT available initially
  // The UI will update when downloads complete via invalidation
  const dbBook = {
    id: bookId,
    ebook_available: false,
    audiobook_available: false
  };
  const isLoadingBook = false;

  // Search for ebook releases
  const {
    data: ebookSearchResults,
    isLoading: isSearchingEbooks,
    error: ebookSearchError,
  } = useQuery({
    queryKey: ['downloads', 'search', bookId, 'ebook', sourceFilter],
    queryFn: () => downloadsApi.searchReleases(bookId!, 'ebook', sourceFilter),
    enabled: open && !!bookId,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    retry: false, // Don't retry on timeout
    gcTime: 0, // Don't cache failed results
  });

  // Search for audiobook releases
  const {
    data: audiobookSearchResults,
    isLoading: isSearchingAudiobooks,
    error: audiobookSearchError,
  } = useQuery({
    queryKey: ['downloads', 'search', bookId, 'audiobook', sourceFilter],
    queryFn: () => downloadsApi.searchReleases(bookId!, 'audiobook', sourceFilter),
    enabled: open && !!bookId,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    retry: false, // Don't retry on timeout
    gcTime: 0, // Don't cache failed results
  });

  // Fetch download tasks for this book to track progress
  const { data: downloadTasks = [] } = useQuery({
    queryKey: ['download-tasks', bookId],
    queryFn: () => downloadsApi.getTasks(0, 100),
    enabled: open && !!bookId,
    refetchInterval: 2000, // Poll every 2 seconds for real-time progress
  });

  // Initialize download states from existing tasks when dialog opens
  useEffect(() => {
    if (!downloadTasks || downloadTasks.length === 0) return;

    setDownloadStates((prev) => {
      const newMap = new Map(prev);
      downloadTasks.forEach((task: any) => {
        // Use loose equality to handle number vs string
        if (task.book_id == bookId && task.download_url) {
          // Set state based on task state
          if (['complete', 'seeding'].includes(task.state)) {
            newMap.set(task.download_url, 'complete');
          } else if (['queued', 'downloading', 'checking'].includes(task.state)) {
            newMap.set(task.download_url, 'downloading');
          }
        }
      });
      return newMap;
    });
  }, [downloadTasks, bookId]);

  // Download mutation
  const downloadMutation = useMutation({
    mutationFn: (params: { release: ReleaseInfo; formatType: 'ebook' | 'audiobook' }) => {
      if (!bookId) {
        throw new Error('Book ID not available');
      }

      // Set state to pending to show spinner
      setDownloadStates((prev) => {
        const newMap = new Map(prev);
        newMap.set(params.release.download_url, 'pending');
        return newMap;
      });

      return downloadsApi.downloadRelease({
        book_id: bookId,
        format_type: params.formatType,
        download_url: params.release.download_url,
        protocol: params.release.protocol,
        release_title: params.release.title,
        indexer: params.release.indexer,
        size_bytes: params.release.size_bytes,
      });
    },
    onSuccess: (data, params) => {
      // Set state to downloading once task is created
      setDownloadStates((prev) => {
        const newMap = new Map(prev);
        newMap.set(params.release.download_url, 'downloading');
        return newMap;
      });

      // Immediately refetch download tasks to show progress bar
      queryClient.invalidateQueries({ queryKey: ['download-tasks', bookId] });
      queryClient.invalidateQueries({ queryKey: ['download-tasks'] });

      // DON'T invalidate search results here - it causes the component to re-render
      // with fresh data which wipes out our downloadStates map
      // Search results will be invalidated when download completes (see useEffect below)

      toast.success('Download started', {
        description: data.message,
      });
    },
    onError: (err: Error, params) => {
      // Clear download state on error
      setDownloadStates((prev) => {
        const newMap = new Map(prev);
        newMap.delete(params.release.download_url);
        return newMap;
      });

      toast.error('Download failed', {
        description: err.message,
      });
    },
  });

  // Watch for completed downloads and update download states
  useEffect(() => {
    if (!downloadTasks || downloadTasks.length === 0) return;

    const completedTasks = downloadTasks.filter((t: any) =>
      ['complete', 'seeding'].includes(t.state) &&
      t.book_id == bookId &&  // Use loose equality
      !completedTasksRef.current.has(t.id)
    );

    if (completedTasks.length > 0) {
      // Mark tasks as seen
      completedTasks.forEach((t: any) => completedTasksRef.current.add(t.id));

      // Update download states to 'complete'
      setDownloadStates((prev) => {
        const newMap = new Map(prev);
        completedTasks.forEach((t: any) => {
          if (t.download_url) {
            newMap.set(t.download_url, 'complete');
          }
        });
        return newMap;
      });

      // Invalidate book queries to refresh availability
      queryClient.invalidateQueries({ queryKey: ['book', bookId] });
      queryClient.invalidateQueries({ queryKey: ['books'] });

      // Re-fetch search results for both formats to update already_downloaded flags
      queryClient.invalidateQueries({ queryKey: ['downloads', 'search', bookId, 'ebook'] });
      queryClient.invalidateQueries({ queryKey: ['downloads', 'search', bookId, 'audiobook'] });

      // Show success notification
      toast.success('Download completed!', {
        description: `${completedTasks[0].release_title} is now available`,
      });
    }
  }, [downloadTasks, bookId, queryClient]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  const getProtocolIcon = (protocol: string) => {
    switch (protocol) {
      case 'torrent':
        return <Wifi className="h-4 w-4" />;
      case 'usenet':
        return <HardDrive className="h-4 w-4" />;
      case 'direct':
        return <Globe className="h-4 w-4" />;
      default:
        return <Download className="h-4 w-4" />;
    }
  };

  const getProtocolColor = (protocol: string) => {
    switch (protocol) {
      case 'torrent':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'usenet':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'direct':
        return 'bg-green-500/20 text-green-400 border-green-500/30';
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  const getFormatIcon = (format: 'ebook' | 'audiobook') => {
    return format === 'ebook' ? <BookOpen className="h-4 w-4" /> : <Headphones className="h-4 w-4" />;
  };


  // Helper function to render release results for a specific format
  const renderReleaseResults = (
    formatType: 'ebook' | 'audiobook',
    searchResults: any,
    isSearching: boolean,
    searchError: Error | null
  ) => {
    if (isSearching) {
      return (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="border rounded-lg p-4 space-y-3">
              <Skeleton className="h-5 w-3/4" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-5 w-16" />
              </div>
              <Skeleton className="h-9 w-32" />
            </div>
          ))}
        </div>
      );
    }

    if (searchError) {
      return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Search className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">Search Failed</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            {(searchError as Error)?.message || 'An error occurred while searching for releases.'}
          </p>
        </div>
      );
    }

    if (!searchResults || searchResults.releases.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Search className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Releases Found</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            We couldn't find any {formatType} releases for this book.
            {directDownloadsEnabled
              ? ' The search includes direct download sources.'
              : ' Enable direct downloads in Settings for more sources.'}
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <div className="text-sm text-muted-foreground mb-4">
          Found {searchResults.total} release{searchResults.total !== 1 ? 's' : ''}
        </div>
        {searchResults.releases.map((release: ReleaseInfo, index: number) => {
          // Find the task in the tasks list - use loose equality for book_id
          const task = downloadTasks.find((t: any) =>
            t.book_id == bookId &&
            t.download_url === release.download_url
          );

          // Get download state from our state map
          const downloadState = downloadStates.get(release.download_url);

          // Determine current state
          const isPending = downloadState === 'pending';
          const isDownloading = downloadState === 'downloading' || (task && ['queued', 'downloading', 'checking'].includes(task.state));
          const isComplete = downloadState === 'complete' || (task && ['complete', 'seeding'].includes(task.state));
          const isFailed = task && task.state === 'error';

          // Check if this format type is already available for the book (only used for badge)
          const isBookAvailable = formatType === 'ebook'
            ? dbBook?.ebook_available
            : dbBook?.audiobook_available;

          return (
            <div
              key={`${release.indexer}-${release.download_url}-${index}`}
              className="border border-border rounded-lg p-4 hover:border-primary/50 transition-colors space-y-3"
            >
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <h4 className="font-medium text-sm leading-snug line-clamp-2 flex-1">
                    {release.title}
                  </h4>
                  {(isBookAvailable || release.already_downloaded) && (
                    <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/30 shrink-0">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Downloaded
                    </Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge
                    variant="outline"
                    className={getProtocolColor(release.protocol)}
                  >
                    {getProtocolIcon(release.protocol)}
                    <span className="ml-1.5">{release.protocol.toUpperCase()}</span>
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    {release.indexer}
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    {formatBytes(release.size_bytes)}
                  </Badge>
                  {release.seeders !== null && release.protocol === 'torrent' && (
                    <Badge
                      variant="outline"
                      className={
                        release.seeders > 10
                          ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                          : release.seeders > 0
                            ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                            : 'bg-red-500/20 text-red-400 border-red-500/30'
                      }
                    >
                      {release.seeders} seeder{release.seeders !== 1 ? 's' : ''}
                    </Badge>
                  )}
                  {release.format && (
                    <Badge variant="outline" className="text-muted-foreground">
                      {release.format}
                    </Badge>
                  )}
                  {release.language && (
                    <Badge variant="outline" className="text-muted-foreground">
                      {release.language}
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-muted-foreground">
                    Score: {release.quality_score.toFixed(1)}
                  </Badge>
                  {release.info_url && (
                    <a
                      href={release.info_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      <span className="text-xs">View</span>
                    </a>
                  )}
                </div>
              </div>

              {/* Show progress bar if downloading */}
              {isPending ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>Starting download...</span>
                </div>
              ) : isDownloading && task ? (
                task.protocol === 'direct' && task.message ? (
                  <DirectDownloadProgress
                    state={task.state}
                    message={task.message}
                    progress={task.progress}
                  />
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        <span>{task.state === 'queued' ? 'Queued' : 'Downloading'}</span>
                      </div>
                      <span className="text-muted-foreground">{task.progress.toFixed(0)}%</span>
                    </div>
                    <Progress value={task.progress} className="h-2" />
                  </div>
                )
              ) : isComplete ? (
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <CheckCircle className="h-4 w-4" />
                  <span>Download Complete</span>
                </div>
              ) : isFailed ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm text-red-400">
                    <XCircle className="h-4 w-4" />
                    <span>{task?.protocol === 'direct' && task?.message ? task.message : 'Download Failed'}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => downloadMutation.mutate({ release, formatType })}
                    disabled={downloadMutation.isPending}
                    className="w-full sm:w-auto"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Retry
                  </Button>
                </div>
              ) : release.already_downloaded || isBookAvailable ? (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CheckCircle className="h-4 w-4 text-green-400" />
                    <span>{release.already_downloaded ? 'Already Downloaded' : 'Book Available'}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => downloadMutation.mutate({ release, formatType })}
                    disabled={downloadMutation.isPending || isComplete}
                    className="ml-auto"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download Again
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  onClick={() => downloadMutation.mutate({ release, formatType })}
                  disabled={downloadMutation.isPending || isComplete}
                  className="w-full sm:w-auto"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Download
                </Button>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            {sourceFilter === 'direct' ? 'Direct Download' : sourceFilter === 'prowlarr' ? 'Download via Prowlarr' : 'Download'} - {book.title}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2 flex-wrap">
            {sourceFilter === 'direct' ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-500/20 text-green-400 text-xs font-medium border border-green-500/30">
                <Globe className="h-3 w-3" />
                Searching direct download sources
              </span>
            ) : sourceFilter === 'prowlarr' ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-400 text-xs font-medium border border-blue-500/30">
                <HardDrive className="h-3 w-3" />
                Searching Prowlarr indexers
              </span>
            ) : (
              <>
                <span>Browse available releases</span>
                {directDownloadsEnabled && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-500/20 text-green-400 text-xs font-medium border border-green-500/30">
                    <Globe className="h-3 w-3" />
                    Direct downloads enabled
                  </span>
                )}
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {(isEnsuring || isLoadingBook) ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="border rounded-lg p-4 space-y-3">
                <Skeleton className="h-5 w-3/4" />
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-24" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-9 w-32" />
              </div>
            ))}
          </div>
        ) : ensureError ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Search className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">Failed to Load Book</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              {(ensureError as Error)?.message || 'An error occurred while loading the book.'}
            </p>
          </div>
        ) : !dbBook ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="border rounded-lg p-4 space-y-3">
                <Skeleton className="h-5 w-3/4" />
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-24" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-9 w-32" />
              </div>
            ))}
          </div>
        ) : dbBook.ebook_available && dbBook.audiobook_available ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <CheckCircle className="h-12 w-12 text-green-400 mb-4" />
            <h3 className="text-lg font-semibold mb-2">Book Fully Available</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              You already own both the ebook and audiobook versions of this book.
            </p>
          </div>
        ) : (
          <Tabs
            value={getValidActiveTab()}
            onValueChange={(value) => setActiveTab(value as 'ebook' | 'audiobook')}
          >
            <TabsList className={`grid w-full ${!dbBook?.ebook_available && !dbBook?.audiobook_available ? 'grid-cols-2' : 'grid-cols-1'}`}>
              {!dbBook?.ebook_available && (
                <TabsTrigger value="ebook" className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Ebooks
                  {ebookSearchResults && ebookSearchResults.total > 0 && (
                    <Badge variant="secondary" className="ml-1">
                      {ebookSearchResults.total}
                    </Badge>
                  )}
                </TabsTrigger>
              )}
              {!dbBook?.audiobook_available && (
                <TabsTrigger value="audiobook" className="flex items-center gap-2">
                  <Headphones className="h-4 w-4" />
                  Audiobooks
                  {audiobookSearchResults && audiobookSearchResults.total > 0 && (
                    <Badge variant="secondary" className="ml-1">
                      {audiobookSearchResults.total}
                    </Badge>
                  )}
                </TabsTrigger>
              )}
            </TabsList>

            {!dbBook?.ebook_available && (
              <TabsContent value="ebook" className="mt-4">
                <div className="max-h-[60vh] overflow-y-auto pr-2">
                  {renderReleaseResults('ebook', ebookSearchResults, isSearchingEbooks, ebookSearchError)}
                </div>
              </TabsContent>
            )}

            {!dbBook?.audiobook_available && (
              <TabsContent value="audiobook" className="mt-4">
                <div className="max-h-[60vh] overflow-y-auto pr-2">
                  {renderReleaseResults('audiobook', audiobookSearchResults, isSearchingAudiobooks, audiobookSearchError)}
                </div>
              </TabsContent>
            )}
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}
