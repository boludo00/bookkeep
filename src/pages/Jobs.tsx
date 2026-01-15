import { useState } from 'react';
import { Play, RefreshCw, Clock } from 'lucide-react';
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
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobsApi } from '@/lib/api';

interface Job {
  name: string;
  type: string;
  interval_seconds: number;
  last_execution: string | null;
  next_execution: string | null;
}

function formatJobName(name: string): string {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatTimeUntil(nextExecution: string | null): string {
  if (!nextExecution) return 'Unknown';
  
  const next = new Date(nextExecution);
  const now = new Date();
  const diffMs = next.getTime() - now.getTime();
  
  if (diffMs <= 0) return 'Now';
  
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffDays > 0) {
    return `in ${diffDays} ${diffDays === 1 ? 'day' : 'days'}`;
  } else if (diffHours > 0) {
    return `in ${diffHours} ${diffHours === 1 ? 'hour' : 'hours'}`;
  } else if (diffMinutes > 0) {
    return `in ${diffMinutes} ${diffMinutes === 1 ? 'minute' : 'minutes'}`;
  } else {
    return `in ${diffSeconds} ${diffSeconds === 1 ? 'second' : 'seconds'}`;
  }
}

export default function Jobs() {
  const queryClient = useQueryClient();
  const [runningJobs, setRunningJobs] = useState<Set<string>>(new Set());

  const { data: jobs = [], isLoading, error, refetch } = useQuery<Job[], Error>({
    queryKey: ['jobs'],
    queryFn: async () => {
      try {
        const result = await jobsApi.getAll();
        console.log('Jobs API response:', result);
        return result;
      } catch (err) {
        console.error('Jobs API error:', err);
        throw err;
      }
    },
    refetchInterval: 30000, // Refresh every 30 seconds to update "next execution" times
    retry: false, // Don't retry on error to show the error immediately
  });

  const runJobMutation = useMutation({
    mutationFn: (jobName: string) => jobsApi.run(jobName),
    onSuccess: (data, jobName) => {
      toast.success('Job triggered', {
        description: `"${formatJobName(jobName)}" has been started.`,
      });
      setRunningJobs(new Set(runningJobs).add(jobName));
      // Refetch jobs to update last_execution and next_execution
      setTimeout(() => {
        refetch();
        setRunningJobs(prev => {
          const next = new Set(prev);
          next.delete(jobName);
          return next;
        });
      }, 2000);
    },
    onError: (error: Error, jobName) => {
      toast.error('Failed to run job', {
        description: error.message || `Could not trigger "${formatJobName(jobName)}".`,
      });
      setRunningJobs(prev => {
        const next = new Set(prev);
        next.delete(jobName);
        return next;
      });
    },
  });

  const handleRunJob = (jobName: string) => {
    setRunningJobs(prev => new Set(prev).add(jobName));
    runJobMutation.mutate(jobName);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Jobs</h1>
        <p className="text-muted-foreground mt-1">
          Bookkeep performs certain maintenance tasks as regularly-scheduled jobs, but they can also be manually triggered below. Manually running a job will not alter its schedule.
        </p>
      </div>

      <div className="bg-card border border-border rounded-lg">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-foreground">JOB NAME</TableHead>
              <TableHead className="text-foreground">TYPE</TableHead>
              <TableHead className="text-foreground">NEXT EXECUTION</TableHead>
              <TableHead className="text-right text-foreground">ACTIONS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading jobs...
                </TableCell>
              </TableRow>
            ) : error ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-destructive">
                  Error loading jobs: {error instanceof Error ? error.message : 'Unknown error'}
                </TableCell>
              </TableRow>
            ) : jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No jobs found
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((job: Job) => {
                const isRunning = runningJobs.has(job.name);
                return (
                  <TableRow key={job.name}>
                    <TableCell className="font-medium text-foreground">
                      {formatJobName(job.name)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="border-border text-foreground">
                        {job.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4" />
                        {formatTimeUntil(job.next_execution)}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => handleRunJob(job.name)}
                        disabled={isRunning || runJobMutation.isPending}
                        className="gap-2"
                      >
                        {isRunning ? (
                          <>
                            <RefreshCw className="h-4 w-4 animate-spin" />
                            Running...
                          </>
                        ) : (
                          <>
                            <Play className="h-4 w-4" />
                            Run Now
                          </>
                        )}
                      </Button>
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
