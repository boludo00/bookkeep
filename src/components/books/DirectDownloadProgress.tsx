import { Search, Clock, Shield, Download } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface DirectDownloadProgressProps {
  state: string;
  message: string;
  progress: number;
}

type Phase = 'discover' | 'resolve' | 'download';

interface PhaseInfo {
  phase: Phase;
  label: string;
  sublabel?: string;
  icon: React.ReactNode;
  progressValue: number | null; // null = indeterminate
}

function parsePhase(state: string, message: string, progress: number): PhaseInfo {
  // Downloading state with real progress
  if (state === 'downloading') {
    // Extract source info from message like "Downloading from Anna's Archive (slow partner server #5)"
    const sourceMatch = message.match(/Downloading from (.+)/);
    const source = sourceMatch ? sourceMatch[1] : undefined;
    return {
      phase: 'download',
      label: source ? `Downloading from ${source}` : 'Downloading',
      icon: <Download className="h-3.5 w-3.5" />,
      progressValue: progress,
    };
  }

  // Queued state, parse message for sub-phases
  if (message.startsWith('Finding sources')) {
    return {
      phase: 'discover',
      label: 'Finding sources',
      icon: <Search className="h-3.5 w-3.5" />,
      progressValue: null,
    };
  }

  if (message.match(/^Source \d+\/\d+/)) {
    return {
      phase: 'discover',
      label: message, // e.g. "Source 2/3"
      icon: <Search className="h-3.5 w-3.5" />,
      progressValue: null,
    };
  }

  if (message === 'Starting countdown...') {
    return {
      phase: 'resolve',
      label: 'Starting countdown',
      sublabel: 'Waiting for download server...',
      icon: <Clock className="h-3.5 w-3.5" />,
      progressValue: null,
    };
  }

  // "Waiting (25s)..." - extract seconds for countdown progress
  const waitMatch = message.match(/Waiting \((\d+)s\)\.\.\./);
  if (waitMatch) {
    const remaining = parseInt(waitMatch[1], 10);
    const total = 33; // countdown starts from ~33s
    const filled = Math.max(0, Math.min(100, ((total - remaining) / total) * 100));
    return {
      phase: 'resolve',
      label: `Server countdown: ${remaining}s`,
      sublabel: 'Waiting for download server...',
      icon: <Clock className="h-3.5 w-3.5" />,
      progressValue: filled,
    };
  }

  if (message === 'Fetching download link...') {
    return {
      phase: 'resolve',
      label: 'Fetching download link',
      icon: <Clock className="h-3.5 w-3.5" />,
      progressValue: null,
    };
  }

  if (message.startsWith('Solving challenge')) {
    return {
      phase: 'resolve',
      label: 'Solving access challenge',
      icon: <Shield className="h-3.5 w-3.5" />,
      progressValue: null,
    };
  }

  // Fallback for unknown messages during queued state
  return {
    phase: state === 'queued' ? 'discover' : 'download',
    label: message || (state === 'queued' ? 'Queued' : 'Downloading'),
    icon: state === 'queued' ? <Search className="h-3.5 w-3.5" /> : <Download className="h-3.5 w-3.5" />,
    progressValue: state === 'downloading' ? progress : null,
  };
}

const PHASES: { key: Phase; label: string }[] = [
  { key: 'discover', label: 'Discover' },
  { key: 'resolve', label: 'Resolve' },
  { key: 'download', label: 'Download' },
];

export function DirectDownloadProgress({ state, message, progress }: DirectDownloadProgressProps) {
  const info = parsePhase(state, message, progress);
  const isIndeterminate = info.progressValue === null;

  return (
    <div className="space-y-2">
      {/* Phase dots */}
      <div className="flex items-center gap-3">
        {PHASES.map((p, i) => {
          const isActive = p.key === info.phase;
          const phaseIndex = PHASES.findIndex(ph => ph.key === info.phase);
          const isCompleted = i < phaseIndex;

          return (
            <div key={p.key} className="flex items-center gap-1.5">
              <div
                className={cn(
                  'h-1.5 w-1.5 rounded-full transition-colors',
                  isActive && 'bg-primary animate-pulse',
                  isCompleted && 'bg-primary',
                  !isActive && !isCompleted && 'bg-muted-foreground/30'
                )}
              />
              <span
                className={cn(
                  'text-[10px] font-medium transition-colors',
                  isActive && 'text-primary',
                  isCompleted && 'text-muted-foreground',
                  !isActive && !isCompleted && 'text-muted-foreground/40'
                )}
              >
                {p.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Icon + label */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-muted-foreground min-w-0">
          <span className="text-primary shrink-0">{info.icon}</span>
          <span className="truncate">{info.label}</span>
        </div>
        {info.progressValue !== null && (
          <span className="text-muted-foreground text-xs shrink-0 ml-2">
            {info.progressValue.toFixed(0)}%
          </span>
        )}
      </div>

      {/* Sublabel */}
      {info.sublabel && (
        <p className="text-[11px] text-muted-foreground/60 -mt-1">{info.sublabel}</p>
      )}

      {/* Progress bar */}
      <div className="relative">
        {isIndeterminate ? (
          <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
            <div className="h-full w-1/3 bg-primary rounded-full animate-indeterminate" />
          </div>
        ) : (
          <Progress value={info.progressValue} className="h-2" />
        )}
      </div>
    </div>
  );
}
