import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, CheckCircle, XCircle, Clock, Loader2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { downloadsApi, DownloadLog, DownloadAttempt } from '@/lib/api';

interface DownloadLogPanelProps {
  taskId: number;
  protocol: string;
}

function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return 'N/A';
  const date = new Date(timestamp);
  return date.toLocaleString();
}

function formatDuration(startedAt: string, endedAt: string | null): string {
  if (!endedAt) return 'In progress...';
  const start = new Date(startedAt).getTime();
  const end = new Date(endedAt).getTime();
  const durationMs = end - start;

  if (durationMs < 1000) return `${durationMs}ms`;
  if (durationMs < 60000) return `${(durationMs / 1000).toFixed(1)}s`;
  return `${Math.floor(durationMs / 60000)}m ${Math.floor((durationMs % 60000) / 1000)}s`;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function getSourceTypeBadge(sourceType: string) {
  const colors: Record<string, string> = {
    'aa-slow-nowait': 'bg-green-500/20 text-green-400 border-green-500/30',
    'aa-slow-wait': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    'libgen': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    'zlib': 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    'external': 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };

  const labels: Record<string, string> = {
    'aa-slow-nowait': 'Fast',
    'aa-slow-wait': 'Waitlist',
    'libgen': 'Libgen',
    'zlib': 'Z-Library',
    'external': 'External',
  };

  return (
    <Badge variant="outline" className={`text-xs ${colors[sourceType] || colors.external}`}>
      {labels[sourceType] || sourceType}
    </Badge>
  );
}

function AttemptRow({ attempt, index }: { attempt: DownloadAttempt; index: number }) {
  return (
    <div className={`p-3 rounded-lg border ${attempt.success ? 'border-green-500/30 bg-green-500/5' : 'border-border bg-card/50'}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-muted-foreground">#{index + 1}</span>
            {attempt.success ? (
              <CheckCircle className="h-4 w-4 text-green-500" />
            ) : attempt.ended_at ? (
              <XCircle className="h-4 w-4 text-destructive" />
            ) : (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            )}
            <span className="font-medium text-sm truncate">{attempt.source_name}</span>
            {getSourceTypeBadge(attempt.source_type)}
          </div>

          <div className="text-xs text-muted-foreground space-y-1">
            <div className="flex items-center gap-2">
              <Clock className="h-3 w-3" />
              <span>Duration: {formatDuration(attempt.started_at, attempt.ended_at)}</span>
              {attempt.bytes_downloaded > 0 && (
                <span className="text-foreground">
                  | {formatBytes(attempt.bytes_downloaded)} downloaded
                </span>
              )}
            </div>

            {attempt.error && (
              <div className="text-destructive flex items-start gap-1 mt-1">
                <XCircle className="h-3 w-3 mt-0.5 shrink-0" />
                <span>{attempt.error}</span>
              </div>
            )}

            <div className="flex items-center gap-1 text-muted-foreground/70 mt-1">
              <ExternalLink className="h-3 w-3" />
              <span className="truncate" title={attempt.url}>{attempt.url}</span>
            </div>
          </div>
        </div>

        <div className="text-right shrink-0">
          {attempt.success && (
            <Badge variant="default" className="bg-green-500 hover:bg-green-600">
              Success
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}

export function DownloadLogPanel({ taskId, protocol }: DownloadLogPanelProps) {
  const [open, setOpen] = useState(false);

  const { data: log, isLoading, error } = useQuery({
    queryKey: ['download-log', taskId],
    queryFn: () => downloadsApi.getTaskLog(taskId),
    enabled: open,
    staleTime: 30000,
  });

  // Only show for direct downloads
  if (protocol !== 'direct') {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          title="View download log"
          className="text-muted-foreground hover:text-foreground"
        >
          <FileText className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Download Log
          </DialogTitle>
          <DialogDescription>
            Detailed log of download sources attempted for this task.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] pr-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-muted-foreground">Loading log...</span>
            </div>
          ) : error ? (
            <div className="text-center py-8 text-destructive">
              <XCircle className="h-8 w-8 mx-auto mb-2" />
              <p>Failed to load download log</p>
              <p className="text-sm text-muted-foreground mt-1">
                {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </div>
          ) : log ? (
            <div className="space-y-4">
              {/* Summary */}
              <div className="bg-muted/30 rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Started</span>
                  <span className="text-sm">{formatTimestamp(log.started_at)}</span>
                </div>
                {log.completed_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Completed</span>
                    <span className="text-sm">{formatTimestamp(log.completed_at)}</span>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Result</span>
                  <Badge
                    variant={log.final_result === 'success' ? 'default' : 'destructive'}
                    className={log.final_result === 'success' ? 'bg-green-500' : ''}
                  >
                    {log.final_result || 'In Progress'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Sources Tried</span>
                  <span className="text-sm font-medium">{log.attempts.length}</span>
                </div>
              </div>

              {/* Attempts */}
              {log.attempts.length > 0 ? (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-muted-foreground">Download Attempts</h4>
                  {log.attempts.map((attempt, index) => (
                    <AttemptRow key={index} attempt={attempt} index={index} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-muted-foreground">
                  {log.message || 'No detailed log available'}
                </div>
              )}
            </div>
          ) : null}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
