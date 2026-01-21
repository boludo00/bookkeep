import { useState, useEffect, useRef } from 'react';
import { Download, Clock, CheckCircle, XCircle, Pause, PlayCircle, FolderInput, Trash2, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { downloadsApi } from '@/lib/api';

interface DownloadTask {
  id: number;
  book_id: number;
  format: string;
  source: string;
  release_title: string;
  message?: string;
  client_state?: string;
  download_url: string;
  protocol: string;
  state: string;
  progress: number;
  download_path: string | null;
  import_status?: string;
  import_message?: string;
  imported_at?: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

function getStateBadgeVariant(state: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (state) {
    case 'complete':
    case 'seeding':
      return 'default';
    case 'downloading':
    case 'queued':
    case 'checking':
      return 'secondary';
    case 'error':
      return 'destructive';
    case 'paused':
      return 'outline';
    default:
      return 'outline';
  }
}

function getStateIcon(state: string) {
  switch (state) {
    case 'complete':
    case 'seeding':
      return <CheckCircle className="h-4 w-4" />;
    case 'downloading':
    case 'checking':
      return <Loader2 className="h-4 w-4 animate-spin" />;
    case 'queued':
      return <Clock className="h-4 w-4" />;
    case 'error':
      return <XCircle className="h-4 w-4" />;
    case 'paused':
      return <Pause className="h-4 w-4" />;
    default:
      return null;
  }
}

function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return 'N/A';

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

function getDetailedStatus(state: string, client_state?: string): string {
  if (!client_state) return state.toUpperCase();

  // Map qBittorrent states to human-readable text
  const stateMap: Record<string, string> = {
    'stalledDL': 'Stalled',
    'stalledUP': 'Stalled (Seeding)',
    'downloading': 'Downloading',
    'uploading': 'Seeding',
    'pausedDL': 'Paused',
    'pausedUP': 'Paused (Seeding)',
    'queuedDL': 'Queued',
    'queuedUP': 'Queued (Seeding)',
    'checkingDL': 'Checking',
    'checkingUP': 'Checking',
    'checkingResumeData': 'Checking',
    'metaDL': 'Downloading Metadata',
    'forcedDL': 'Downloading (Forced)',
    'forcedUP': 'Seeding (Forced)',
    'allocating': 'Allocating Space',
    'error': 'Error',
    'missingFiles': 'Missing Files',
  };

  return stateMap[client_state] || client_state;
}

function getImportStatusBadgeVariant(status?: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (!status) return 'outline';

  switch (status) {
    case 'imported':
      return 'default';
    case 'importing':
      return 'secondary';
    case 'failed':
      return 'destructive';
    case 'pending':
    case 'skipped':
      return 'outline';
    default:
      return 'outline';
  }
}

function getImportStatusIcon(status?: string) {
  if (!status) return null;

  switch (status) {
    case 'imported':
      return <CheckCircle className="h-4 w-4" />;
    case 'importing':
      return <Loader2 className="h-4 w-4 animate-spin" />;
    case 'failed':
      return <XCircle className="h-4 w-4" />;
    case 'pending':
      return <Clock className="h-4 w-4" />;
    case 'skipped':
      return <Pause className="h-4 w-4" />;
    default:
      return null;
  }
}

function getImportStatusLabel(status?: string): string {
  if (!status) return 'Not Started';

  switch (status) {
    case 'pending':
      return 'Pending';
    case 'importing':
      return 'Importing';
    case 'imported':
      return 'Imported';
    case 'failed':
      return 'Failed';
    case 'skipped':
      return 'Skipped';
    default:
      return status.toUpperCase();
  }
}

// Helper function to get initial completed tasks from localStorage
const getInitialCompletedTasks = () => {
  try {
    const stored = localStorage.getItem('seen_completed_downloads');
    return stored ? new Set<number>(JSON.parse(stored)) : new Set<number>();
  } catch {
    return new Set<number>();
  }
};

export default function Downloads() {
  const queryClient = useQueryClient();
  const [filterState, setFilterState] = useState<string | undefined>(undefined);
  const completedTasksRef = useRef<Set<number>>(getInitialCompletedTasks());

  const { data: tasks = [], isLoading, error, refetch } = useQuery<DownloadTask[], Error>({
    queryKey: ['download-tasks', filterState],
    queryFn: async () => {
      try {
        const result = await downloadsApi.getTasks(0, 100, filterState);
        return result;
      } catch (err) {
        console.error('Download tasks API error:', err);
        throw err;
      }
    },
    refetchInterval: 2000, // Refresh every 2 seconds for real-time progress
    retry: false,
  });

  // Import mutation
  const importMutation = useMutation({
    mutationFn: (taskId: number) => downloadsApi.importDownload(taskId),
    onSuccess: (data) => {
      toast.success('Import successful', {
        description: data.message,
      });
      // Refresh the tasks list (task will be removed after import)
      queryClient.invalidateQueries({ queryKey: ['download-tasks'] });
      // Also invalidate book queries to update availability
      queryClient.invalidateQueries({ queryKey: ['books'] });
      queryClient.invalidateQueries({ queryKey: ['hardcover'] });
    },
    onError: (err: Error) => {
      toast.error('Import failed', {
        description: err.message,
      });
    },
  });

  // Delete task mutation
  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => downloadsApi.deleteTask(taskId),
    onSuccess: (data) => {
      toast.success('Task deleted', {
        description: data.message,
      });
      // Refresh the tasks list
      queryClient.invalidateQueries({ queryKey: ['download-tasks'] });
    },
    onError: (err: Error) => {
      toast.error('Delete failed', {
        description: err.message,
      });
    },
  });

  // Clear visible tasks mutation (respects filter)
  const clearAllMutation = useMutation({
    mutationFn: async () => {
      // If filtering, delete only the visible tasks one by one
      if (filterState) {
        const tasksToDelete = tasks.filter(t => {
          // Only delete eligible tasks
          if (t.state === 'error' || t.state === 'paused') return true;
          // For completed, would need to check if imported (backend will validate)
          if (t.state === 'complete' || t.state === 'seeding') return true;
          return false;
        });

        // Delete each task individually
        const results = await Promise.allSettled(
          tasksToDelete.map(t => downloadsApi.deleteTask(t.id))
        );

        const successCount = results.filter(r => r.status === 'fulfilled').length;
        const failCount = results.filter(r => r.status === 'rejected').length;

        return {
          success: true,
          message: `Cleared ${successCount} task(s)${failCount > 0 ? ` (${failCount} failed)` : ''}`,
          deleted_count: successCount
        };
      } else {
        // No filter - use bulk clear endpoint
        return downloadsApi.clearTasks();
      }
    },
    onSuccess: (data) => {
      toast.success('Tasks cleared', {
        description: data.message,
      });
      // Refresh the tasks list
      queryClient.invalidateQueries({ queryKey: ['download-tasks'] });
    },
    onError: (err: Error) => {
      toast.error('Clear failed', {
        description: err.message,
      });
    },
  });

  const activeTasks = tasks.filter(t =>
    ['queued', 'downloading', 'checking'].includes(t.state)
  );

  const completedTasks = tasks.filter(t =>
    ['complete', 'seeding'].includes(t.state)
  );

  const failedTasks = tasks.filter(t =>
    t.state === 'error'
  );

  const importedTasks = tasks.filter(t =>
    t.import_status === 'imported'
  );

  // Watch for newly completed downloads and invalidate book queries
  useEffect(() => {
    if (!tasks || tasks.length === 0) return;

    const newlyCompleted = tasks.filter((t: DownloadTask) =>
      ['complete', 'seeding'].includes(t.state) &&
      !completedTasksRef.current.has(t.id)
    );

    if (newlyCompleted.length > 0) {
      // Mark as seen
      newlyCompleted.forEach((t: DownloadTask) => completedTasksRef.current.add(t.id));

      // Save to localStorage
      try {
        localStorage.setItem('seen_completed_downloads', JSON.stringify([...completedTasksRef.current]));
      } catch (e) {
        console.error('Failed to save seen downloads:', e);
      }

      // Invalidate all book-related queries to refresh availability
      newlyCompleted.forEach((t: DownloadTask) => {
        queryClient.invalidateQueries({ queryKey: ['hardcover', 'book', String(t.book_id)] });
        queryClient.invalidateQueries({ queryKey: ['book', t.book_id] });
      });

      // Also invalidate book lists
      queryClient.invalidateQueries({ queryKey: ['books'] });
      queryClient.invalidateQueries({ queryKey: ['hardcover'] });

      // Show notification
      toast.success('Download completed!', {
        description: `${newlyCompleted[0].release_title || 'Book'} is now available`,
      });
    }
  }, [tasks, queryClient]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Downloads</h1>
        <p className="text-muted-foreground mt-1">
          Monitor your active downloads and view download history.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Active Downloads</p>
              <p className="text-2xl font-bold text-foreground">{activeTasks.length}</p>
            </div>
            <Download className="h-8 w-8 text-blue-500" />
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Completed</p>
              <p className="text-2xl font-bold text-foreground">{completedTasks.length}</p>
            </div>
            <CheckCircle className="h-8 w-8 text-green-500" />
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Imported</p>
              <p className="text-2xl font-bold text-foreground">{importedTasks.length}</p>
            </div>
            <FolderInput className="h-8 w-8 text-purple-500" />
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Failed</p>
              <p className="text-2xl font-bold text-foreground">{failedTasks.length}</p>
            </div>
            <XCircle className="h-8 w-8 text-red-500" />
          </div>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2">
        <Button
          variant={filterState === undefined ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilterState(undefined)}
        >
          All
        </Button>
        <Button
          variant={filterState === 'downloading' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilterState('downloading')}
        >
          Downloading
        </Button>
        <Button
          variant={filterState === 'complete' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilterState('complete')}
        >
          Complete
        </Button>
        <Button
          variant={filterState === 'error' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilterState('error')}
        >
          Failed
        </Button>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => clearAllMutation.mutate()}
          disabled={clearAllMutation.isPending || tasks.length === 0}
          title={filterState ? `Clear all ${filterState} tasks` : 'Clear imported/failed tasks from history'}
          className="ml-auto"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          {filterState ? `Clear ${filterState}` : 'Clear History'}
        </Button>
      </div>

      {/* Downloads Table */}
      <div className="bg-card border border-border rounded-lg">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-foreground">TITLE</TableHead>
              <TableHead className="text-foreground">FORMAT</TableHead>
              <TableHead className="text-foreground">DOWNLOAD</TableHead>
              <TableHead className="text-foreground">IMPORT</TableHead>
              <TableHead className="text-foreground">PROGRESS</TableHead>
              <TableHead className="text-foreground">LOCATION</TableHead>
              <TableHead className="text-foreground">CREATED</TableHead>
              <TableHead className="text-foreground">ACTIONS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-muted-foreground">
                  Loading downloads...
                </TableCell>
              </TableRow>
            ) : error ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-destructive">
                  Error loading downloads: {error instanceof Error ? error.message : 'Unknown error'}
                </TableCell>
              </TableRow>
            ) : tasks.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
                  <Download className="h-12 w-12 mx-auto mb-2 text-muted-foreground/50" />
                  <p>No downloads found</p>
                  <p className="text-sm mt-1">Your download history will appear here</p>
                </TableCell>
              </TableRow>
            ) : (
              tasks.map((task: DownloadTask) => {
                return (
                  <TableRow key={task.id}>
                    <TableCell className="font-medium text-foreground max-w-md">
                      <div className="truncate" title={task.release_title}>
                        {task.release_title}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        Book ID: {task.book_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="border-border text-foreground">
                        {task.format.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStateBadgeVariant(task.state)} className="gap-1">
                        {getStateIcon(task.state)}
                        {getDetailedStatus(task.state, task.client_state)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getImportStatusBadgeVariant(task.import_status)} className="gap-1">
                        {getImportStatusIcon(task.import_status)}
                        {getImportStatusLabel(task.import_status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="w-full max-w-[120px]">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">
                            {task.progress.toFixed(0)}%
                          </span>
                        </div>
                        <Progress value={task.progress} className="h-2" />
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-xs">
                      {task.download_path ? (
                        <div className="flex items-center gap-1">
                          <span className="text-xs truncate" title={task.download_path}>
                            {task.download_path}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/50">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatTimestamp(task.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {/* Show import button only when download is complete AND import hasn't succeeded yet */}
                        {(task.state === 'complete' || task.state === 'seeding') &&
                         task.import_status !== 'imported' &&
                         task.import_status !== 'importing' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => importMutation.mutate(task.id)}
                            disabled={importMutation.isPending}
                            title={
                              task.import_status === 'failed'
                                ? 'Retry import'
                                : task.import_status === 'pending'
                                ? 'Import to library'
                                : 'Import to library'
                            }
                          >
                            <FolderInput className="h-4 w-4" />
                          </Button>
                        )}
                        {/* Show delete button for completed/failed tasks */}
                        {(task.state === 'complete' || task.state === 'seeding' || task.state === 'error' || task.state === 'paused') && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => deleteMutation.mutate(task.id)}
                            disabled={deleteMutation.isPending}
                            title="Delete task"
                            className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
