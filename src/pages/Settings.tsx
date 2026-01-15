import { useState, useEffect } from 'react';
import { Save, TestTube, CheckCircle, XCircle, Eye, EyeOff, Lock, Plus, Edit, Trash2, RefreshCw, Play, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi, readarrApi, jobsApi, bookloreApi, type BookloreServer } from '@/lib/api';

interface ReadarrServer {
  id: number;
  name: string;
  hostname: string;
  port: number;
  use_ssl: boolean;
  api_key: string;
  url_base?: string;
  is_default: boolean;
  is_audiobook: boolean;
  ebook_quality_profile_id?: number;
  ebook_root_folder?: string;
  ebook_tags?: string;
  audiobook_quality_profile_id?: number;
  audiobook_root_folder?: string;
  audiobook_tags?: string;
}

interface Job {
  name: string;
  type: string;
  interval_seconds: number;
  last_execution: string | null;
  next_execution: string | null;
  is_enabled?: boolean;
}

interface IntervalOption {
  value: number;
  label: string;
}

interface BookloreServerForm {
  name: string;
  url: string;
  username: string;
  password: string;
  is_default: boolean;
}

function formatJobName(name: string): string {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatTimeUntilStatic(nextExecution: string | null): string {
  if (!nextExecution) return 'Unknown';
  
  // Treat the time as UTC if it doesn't have a timezone indicator
  const timeStr = nextExecution.endsWith('Z') ? nextExecution : nextExecution + 'Z';
  const next = new Date(timeStr);
  const now = new Date();
  const diffMs = next.getTime() - now.getTime();
  
  if (diffMs <= 0) return 'Now';
  
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffDays > 0) {
    const remainingHours = diffHours % 24;
    return `in ${diffDays}d ${remainingHours}h`;
  } else if (diffHours > 0) {
    const remainingMinutes = diffMinutes % 60;
    return `in ${diffHours}h ${remainingMinutes}m`;
  } else if (diffMinutes > 0) {
    const remainingSeconds = diffSeconds % 60;
    return `in ${diffMinutes}m ${remainingSeconds}s`;
  } else {
    return `in ${diffSeconds}s`;
  }
}

// Live countdown component that updates every second
function Countdown({ nextExecution }: { nextExecution: string | null }) {
  const [timeLeft, setTimeLeft] = useState(formatTimeUntilStatic(nextExecution));
  
  useEffect(() => {
    if (!nextExecution) return;
    
    // Update immediately
    setTimeLeft(formatTimeUntilStatic(nextExecution));
    
    // Update every second
    const interval = setInterval(() => {
      setTimeLeft(formatTimeUntilStatic(nextExecution));
    }, 1000);
    
    return () => clearInterval(interval);
  }, [nextExecution]);
  
  return <span>{timeLeft}</span>;
}

export default function Settings() {
  const [showHardcoverToken, setShowHardcoverToken] = useState(false);
  const [hardcoverToken, setHardcoverToken] = useState('');
  const [showServerModal, setShowServerModal] = useState(false);
  const [editingServer, setEditingServer] = useState<ReadarrServer | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [runningJobs, setRunningJobs] = useState<Set<string>>(new Set());
  
  // Job editing state
  const [showJobModal, setShowJobModal] = useState(false);
  const [editingJob, setEditingJob] = useState<Job | null>(null);
  const [selectedInterval, setSelectedInterval] = useState<number>(0);
  
  // Booklore state
  const [showBookloreModal, setShowBookloreModal] = useState(false);
  const [editingBookloreServer, setEditingBookloreServer] = useState<BookloreServer | null>(null);
  const [showBooklorePassword, setShowBooklorePassword] = useState(false);
  const [testingBookloreConnection, setTestingBookloreConnection] = useState(false);
  const [bookloreTestResult, setBookloreTestResult] = useState<{ success: boolean; libraries?: any[]; error?: string } | null>(null);
  const [bookloreForm, setBookloreForm] = useState<BookloreServerForm>({
    name: '',
    url: '',
    username: '',
    password: '',
    is_default: false,
  });
  
  // Server form state
  const [serverForm, setServerForm] = useState({
    name: '',
    hostname: 'http://',
    port: 8787,
    use_ssl: false,
    api_key: '',
    url_base: '',
    is_default: false,
    is_audiobook: false,
    ebook_quality_profile_id: undefined as number | undefined,
    ebook_root_folder: undefined as string | undefined,
    ebook_tags: undefined as string | undefined,
    audiobook_quality_profile_id: undefined as number | undefined,
    audiobook_root_folder: undefined as string | undefined,
    audiobook_tags: undefined as string | undefined,
  });

  // Test connection results
  const [testResults, setTestResults] = useState<{
    quality_profiles?: Array<{ id: number; name: string }>;
    root_folders?: Array<{ path: string }>;
    tags?: Array<{ id: number; label: string }>;
  } | null>(null);

  const queryClient = useQueryClient();

  // Fetch Hardcover token status
  const { data: tokenStatus } = useQuery({
    queryKey: ['hardcover-token-status'],
    queryFn: () => settingsApi.getHardcoverToken(),
  });

  // Fetch Readarr servers
  const { data: servers = [], refetch: refetchServers } = useQuery({
    queryKey: ['readarr-servers'],
    queryFn: () => readarrApi.getAll(),
  });

  // Fetch Jobs
  const { data: jobs = [], isLoading: jobsLoading, error: jobsError, refetch: refetchJobs } = useQuery<Job[], Error>({
    queryKey: ['jobs'],
    queryFn: async () => {
      try {
        const result = await jobsApi.getAll();
        return result;
      } catch (err: any) {
        console.error('Jobs API error:', err);
        // If it's a 404, the route might not be registered (server needs restart)
        if (err?.message?.includes('404') || err?.message?.includes('Not Found')) {
          throw new Error('Jobs endpoint not found. Please restart the backend server to load the jobs router.');
        }
        throw err;
      }
    },
    refetchInterval: 5000, // Refresh every 5 seconds for real-time countdown
    retry: false,
  });

  // Fetch Booklore servers
  const { data: bookloreServers = [], refetch: refetchBookloreServers } = useQuery({
    queryKey: ['booklore-servers'],
    queryFn: () => bookloreApi.getAll(),
  });

  // Fetch job interval options
  const { data: intervalOptions = [] } = useQuery<IntervalOption[], Error>({
    queryKey: ['job-intervals'],
    queryFn: () => jobsApi.getIntervals(),
  });

  // Update token state when backend status loads
  useEffect(() => {
    if (tokenStatus) {
      setHardcoverToken(tokenStatus.hardcover_api_token || '');
    }
  }, [tokenStatus]);

  // Save Hardcover token mutation
  const saveHardcoverTokenMutation = useMutation({
    mutationFn: (token: string) => settingsApi.setHardcoverToken(token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hardcover-token-status'] });
      toast.success('Hardcover API token saved!');
    },
    onError: (error: Error) => {
      toast.error('Failed to save token', {
        description: error.message,
      });
    },
  });

  // Create/Update server mutation
  const saveServerMutation = useMutation({
    mutationFn: (server: any) => {
      if (editingServer) {
        return readarrApi.update(editingServer.id, server);
      }
      return readarrApi.create(server);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['readarr-servers'] });
      toast.success(`Readarr server ${editingServer ? 'updated' : 'created'}!`);
      setShowServerModal(false);
      resetServerForm();
    },
    onError: (error: Error) => {
      toast.error(`Failed to ${editingServer ? 'update' : 'create'} server`, {
        description: error.message,
      });
    },
  });

  // Delete server mutation
  const deleteServerMutation = useMutation({
    mutationFn: (id: number) => readarrApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['readarr-servers'] });
      toast.success('Server deleted!');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete server', {
        description: error.message,
      });
    },
  });

  // Poll for job status
  const pollJobStatus = async (runId: string, jobName: string, toastId: string | number) => {
    const startTime = Date.now();
    const maxWaitTime = 10 * 60 * 1000; // 10 minutes max
    const pollInterval = 2000; // Poll every 2 seconds
    
    const poll = async () => {
      try {
        const status = await jobsApi.getStatus(runId);
        const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
        
        if (status.status === 'running') {
          // Update toast with elapsed time
          toast.loading(`Running "${formatJobName(jobName)}"...`, {
            id: toastId,
            description: `Elapsed: ${elapsedSeconds}s`,
          });
          
          // Continue polling if not timed out
          if (Date.now() - startTime < maxWaitTime) {
            setTimeout(poll, pollInterval);
          } else {
            // Timeout - assume it's still running in background
            toast.dismiss(toastId);
            toast.info('Job still running', {
              description: `"${formatJobName(jobName)}" is taking longer than expected. Check the logs for progress.`,
              duration: 5000,
            });
            setRunningJobs(prev => {
              const next = new Set(prev);
              next.delete(jobName);
              return next;
            });
            refetchJobs();
          }
        } else if (status.status === 'completed') {
          const durationStr = status.duration_seconds 
            ? `${Math.round(status.duration_seconds)}s` 
            : 'unknown time';
          toast.dismiss(toastId);
          toast.success('Job completed', {
            description: `"${formatJobName(jobName)}" finished in ${durationStr}.`,
            duration: 5000,
          });
          setRunningJobs(prev => {
            const next = new Set(prev);
            next.delete(jobName);
            return next;
          });
          refetchJobs();
        } else if (status.status === 'failed') {
          toast.dismiss(toastId);
          toast.error('Job failed', {
            description: status.error || `"${formatJobName(jobName)}" encountered an error.`,
            duration: 8000,
          });
          setRunningJobs(prev => {
            const next = new Set(prev);
            next.delete(jobName);
            return next;
          });
          refetchJobs();
        }
      } catch (error) {
        // If status check fails, assume job is done and stop polling
        toast.dismiss(toastId);
        toast.info('Job status unknown', {
          description: `Could not check status for "${formatJobName(jobName)}". Check the logs.`,
          duration: 5000,
        });
        setRunningJobs(prev => {
          const next = new Set(prev);
          next.delete(jobName);
          return next;
        });
        refetchJobs();
      }
    };
    
    // Start polling after a short delay
    setTimeout(poll, pollInterval);
  };

  // Run job mutation
  const runJobMutation = useMutation({
    mutationFn: (jobName: string) => jobsApi.run(jobName),
    onSuccess: (data, jobName) => {
      // Show loading toast
      const toastId = toast.loading(`Running "${formatJobName(jobName)}"...`, {
        description: 'Starting...',
      });
      
      setRunningJobs(new Set(runningJobs).add(jobName));
      
      // Start polling for status
      pollJobStatus(data.run_id, jobName, toastId);
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

  // Update job mutation
  const updateJobMutation = useMutation({
    mutationFn: ({ jobName, intervalSeconds }: { jobName: string; intervalSeconds: number }) =>
      jobsApi.update(jobName, intervalSeconds),
    onSuccess: (data, variables) => {
      toast.success('Job updated', {
        description: `"${formatJobName(variables.jobName)}" schedule has been updated.`,
      });
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setShowJobModal(false);
      setEditingJob(null);
    },
    onError: (error: Error) => {
      toast.error('Failed to update job', {
        description: error.message,
      });
    },
  });

  const handleEditJob = (job: Job) => {
    setEditingJob(job);
    setSelectedInterval(job.interval_seconds);
    setShowJobModal(true);
  };

  const handleSaveJobSchedule = () => {
    if (!editingJob || !selectedInterval) return;
    updateJobMutation.mutate({
      jobName: editingJob.name,
      intervalSeconds: selectedInterval,
    });
  };

  const formatInterval = (seconds: number): string => {
    const option = intervalOptions.find(opt => opt.value === seconds);
    if (option) return option.label;
    
    // Fallback formatting
    if (seconds < 60) return `${seconds} seconds`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours`;
    return `${Math.floor(seconds / 86400)} days`;
  };

  // Booklore mutations
  const saveBookloreServerMutation = useMutation({
    mutationFn: (server: BookloreServerForm) => {
      if (editingBookloreServer) {
        return bookloreApi.update(editingBookloreServer.id, server);
      }
      return bookloreApi.create(server);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['booklore-servers'] });
      toast.success(`Booklore server ${editingBookloreServer ? 'updated' : 'created'}!`);
      setShowBookloreModal(false);
      resetBookloreForm();
    },
    onError: (error: Error) => {
      toast.error(`Failed to ${editingBookloreServer ? 'update' : 'create'} server`, {
        description: error.message,
      });
    },
  });

  const deleteBookloreServerMutation = useMutation({
    mutationFn: (id: number) => bookloreApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['booklore-servers'] });
      toast.success('Booklore server deleted!');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete server', {
        description: error.message,
      });
    },
  });

  const resetBookloreForm = () => {
    setBookloreForm({
      name: '',
      url: '',
      username: '',
      password: '',
      is_default: false,
    });
    setEditingBookloreServer(null);
    setBookloreTestResult(null);
  };

  const handleAddBookloreServer = () => {
    resetBookloreForm();
    setShowBookloreModal(true);
  };

  const handleEditBookloreServer = (server: BookloreServer) => {
    setEditingBookloreServer(server);
    setBookloreForm({
      name: server.name,
      url: server.url,
      username: server.username,
      password: '', // Don't populate password for security
      is_default: server.is_default,
    });
    setShowBookloreModal(true);
  };

  const handleTestBookloreConnection = async () => {
    if (!bookloreForm.url || !bookloreForm.username || !bookloreForm.password) {
      toast.error('Please fill in URL, username, and password');
      return;
    }

    setTestingBookloreConnection(true);
    try {
      const result = await bookloreApi.testConnection({
        url: bookloreForm.url,
        username: bookloreForm.username,
        password: bookloreForm.password,
      });

      setBookloreTestResult(result);
      if (result.success) {
        toast.success('Connection successful!', {
          description: `Found ${result.libraries?.length || 0} libraries`,
        });
      } else {
        toast.error('Connection failed', {
          description: result.error,
        });
      }
    } catch (error: any) {
      toast.error('Connection test failed', {
        description: error.message,
      });
      setBookloreTestResult(null);
    } finally {
      setTestingBookloreConnection(false);
    }
  };

  const handleSaveBookloreServer = () => {
    if (!bookloreForm.name || !bookloreForm.url || !bookloreForm.username) {
      toast.error('Please fill in required fields');
      return;
    }

    // For new servers, password is required
    if (!editingBookloreServer && !bookloreForm.password) {
      toast.error('Password is required');
      return;
    }

    saveBookloreServerMutation.mutate(bookloreForm);
  };

  const resetServerForm = () => {
    setServerForm({
      name: '',
      hostname: 'http://',
      port: 8787,
      use_ssl: false,
      api_key: '',
      url_base: '',
      is_default: false,
      is_audiobook: false,
      ebook_quality_profile_id: undefined,
      ebook_root_folder: undefined,
      ebook_tags: undefined,
      audiobook_quality_profile_id: undefined,
      audiobook_root_folder: undefined,
      audiobook_tags: undefined,
    });
    setEditingServer(null);
    setTestResults(null);
  };

  const handleAddServer = () => {
    resetServerForm();
    setShowServerModal(true);
  };

  const handleEditServer = (server: ReadarrServer) => {
    setEditingServer(server);
    setServerForm({
      name: server.name,
      hostname: server.hostname,
      port: server.port,
      use_ssl: server.use_ssl,
      api_key: server.api_key,
      url_base: server.url_base || '',
      is_default: server.is_default,
      is_audiobook: server.is_audiobook,
      ebook_quality_profile_id: server.ebook_quality_profile_id,
      ebook_root_folder: server.ebook_root_folder,
      ebook_tags: server.ebook_tags,
      audiobook_quality_profile_id: server.audiobook_quality_profile_id,
      audiobook_root_folder: server.audiobook_root_folder,
      audiobook_tags: server.audiobook_tags,
    });
    setShowServerModal(true);
  };

  const handleTestConnection = async () => {
    if (!serverForm.hostname || !serverForm.api_key) {
      toast.error('Please fill in hostname and API key');
      return;
    }

    setTestingConnection(true);
    try {
      const result = await readarrApi.testConnection({
        hostname: serverForm.hostname.replace(/^https?:\/\//, '').split(':')[0].split('/')[0],
        port: serverForm.port,
        use_ssl: serverForm.use_ssl,
        api_key: serverForm.api_key,
        url_base: serverForm.url_base || undefined,
      });

      if (result.success) {
        setTestResults({
          quality_profiles: result.quality_profiles || [],
          root_folders: result.root_folders || [],
          tags: result.tags || [],
        });
        toast.success('Connection successful!');
      } else {
        toast.error('Connection failed', {
          description: result.error,
        });
        setTestResults(null);
      }
    } catch (error: any) {
      toast.error('Connection test failed', {
        description: error.message,
      });
      setTestResults(null);
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSaveServer = () => {
    if (!serverForm.name || !serverForm.hostname || !serverForm.api_key) {
      toast.error('Please fill in required fields');
      return;
    }

    // Validate required fields based on server type
    if (!serverForm.is_audiobook) {
      if (!serverForm.ebook_quality_profile_id || !serverForm.ebook_root_folder) {
        toast.error('Please select ebook quality profile and root folder');
        return;
      }
    } else {
      if (!serverForm.audiobook_quality_profile_id || !serverForm.audiobook_root_folder) {
        toast.error('Please select audiobook quality profile and root folder');
        return;
      }
    }

    // Clean hostname (remove protocol if present)
    const cleanHostname = serverForm.hostname.replace(/^https?:\/\//, '').split(':')[0].split('/')[0];

    // Prepare payload - ensure numbers are integers, not NaN
    const payload: any = {
      ...serverForm,
      hostname: cleanHostname,
    };

    // Clean up undefined/NaN values and ensure integers
    if (payload.ebook_quality_profile_id === undefined || isNaN(payload.ebook_quality_profile_id)) {
      payload.ebook_quality_profile_id = null;
    } else {
      payload.ebook_quality_profile_id = parseInt(payload.ebook_quality_profile_id.toString(), 10);
    }

    if (payload.audiobook_quality_profile_id === undefined || isNaN(payload.audiobook_quality_profile_id)) {
      payload.audiobook_quality_profile_id = null;
    } else {
      payload.audiobook_quality_profile_id = parseInt(payload.audiobook_quality_profile_id.toString(), 10);
    }

    // Ensure port is an integer
    payload.port = parseInt(payload.port.toString(), 10);

    saveServerMutation.mutate(payload);
  };

  const handleSaveHardcoverToken = () => {
    if (tokenStatus?.hardcover_api_token_source !== 'env' && hardcoverToken !== tokenStatus?.hardcover_api_token) {
      saveHardcoverTokenMutation.mutate(hardcoverToken);
    }
  };

  const isHardcoverTokenFromEnv = tokenStatus?.hardcover_api_token_source === 'env';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="text-muted-foreground mt-1">
          Configure your Bookkeep integrations
        </p>
      </div>

      <Tabs defaultValue="general" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="jobs">Jobs & Cache</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6 mt-6">
          {/* Hardcover Settings */}
          <Card className="bg-card border-border">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-foreground">Hardcover.app</CardTitle>
              <CardDescription>
                Configure your Hardcover API token for book metadata
              </CardDescription>
            </div>
            {isHardcoverTokenFromEnv && (
              <Badge variant="secondary" className="flex items-center gap-1">
                <Lock className="h-3 w-3" />
                Environment Variable
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="hardcover-token" className="text-foreground">
              API Token
            </Label>
            <div className="relative">
              <Input
                id="hardcover-token"
                type={showHardcoverToken ? "text" : "password"}
                placeholder="Enter your Hardcover API token"
                value={hardcoverToken}
                onChange={(e) => setHardcoverToken(e.target.value)}
                className="bg-secondary border-border pr-10"
                disabled={isHardcoverTokenFromEnv}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowHardcoverToken(!showHardcoverToken)}
                disabled={isHardcoverTokenFromEnv}
              >
                {showHardcoverToken ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {isHardcoverTokenFromEnv && (
              <p className="text-xs text-muted-foreground">
                Token is set via environment variable and cannot be changed here.
              </p>
            )}
          </div>
          <div className="flex justify-end">
            <Button
              onClick={handleSaveHardcoverToken}
              disabled={isHardcoverTokenFromEnv || saveHardcoverTokenMutation.isPending}
              size="sm"
            >
              <Save className="h-4 w-4 mr-2" />
              Save Token
            </Button>
          </div>
        </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="services" className="space-y-6 mt-6">
          {/* Booklore Settings */}
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-foreground">Booklore</CardTitle>
              <CardDescription>
                Configure your Booklore server for checking book availability. Booklore is used to determine when books have been downloaded and are ready to read.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Existing Booklore servers */}
              {bookloreServers.map((server: BookloreServer) => (
                <div
                  key={server.id}
                  className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/50"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-foreground">{server.name}</span>
                      {server.is_default && (
                        <Badge variant="secondary" className="text-xs">Default</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{server.url}</p>
                    <p className="text-xs text-muted-foreground mt-1">User: {server.username}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEditBookloreServer(server)}
                    >
                      <Edit className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => deleteBookloreServerMutation.mutate(server.id)}
                      disabled={deleteBookloreServerMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}

              {/* Add new Booklore server button */}
              <button
                onClick={handleAddBookloreServer}
                className="w-full p-4 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-secondary/50 transition-colors flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
              >
                <Plus className="h-5 w-5" />
                Add Booklore Server
              </button>
            </CardContent>
          </Card>

          {/* Booklore Modal */}
          <Dialog open={showBookloreModal} onOpenChange={setShowBookloreModal}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>
                  {editingBookloreServer ? 'Edit Booklore Server' : 'Add Booklore Server'}
                </DialogTitle>
                <DialogDescription>
                  Configure your Booklore server connection
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="booklore-name" className="text-foreground">Name *</Label>
                  <Input
                    id="booklore-name"
                    value={bookloreForm.name}
                    onChange={(e) => setBookloreForm({ ...bookloreForm, name: e.target.value })}
                    placeholder="e.g., Main Library"
                    className="bg-secondary border-border"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="booklore-url" className="text-foreground">URL *</Label>
                  <Input
                    id="booklore-url"
                    value={bookloreForm.url}
                    onChange={(e) => setBookloreForm({ ...bookloreForm, url: e.target.value })}
                    placeholder="https://booklore.example.com"
                    className="bg-secondary border-border"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="booklore-username" className="text-foreground">Username *</Label>
                  <Input
                    id="booklore-username"
                    value={bookloreForm.username}
                    onChange={(e) => setBookloreForm({ ...bookloreForm, username: e.target.value })}
                    placeholder="admin"
                    className="bg-secondary border-border"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="booklore-password" className="text-foreground">
                    Password {editingBookloreServer ? '(leave blank to keep current)' : '*'}
                  </Label>
                  <div className="relative">
                    <Input
                      id="booklore-password"
                      type={showBooklorePassword ? "text" : "password"}
                      value={bookloreForm.password}
                      onChange={(e) => setBookloreForm({ ...bookloreForm, password: e.target.value })}
                      className="bg-secondary border-border pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-0 top-0 h-full px-3"
                      onClick={() => setShowBooklorePassword(!showBooklorePassword)}
                    >
                      {showBooklorePassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="booklore-default"
                    checked={bookloreForm.is_default}
                    onCheckedChange={(checked) =>
                      setBookloreForm({ ...bookloreForm, is_default: checked === true })
                    }
                  />
                  <Label htmlFor="booklore-default" className="font-normal cursor-pointer">
                    Default Server
                  </Label>
                </div>

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTestBookloreConnection}
                  disabled={testingBookloreConnection || !bookloreForm.url || !bookloreForm.username || !bookloreForm.password}
                  className="w-full"
                >
                  <TestTube className="h-4 w-4 mr-2" />
                  {testingBookloreConnection ? 'Testing...' : 'Test Connection'}
                </Button>

                {bookloreTestResult && (
                  <div className={`p-3 rounded-lg ${bookloreTestResult.success ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                    <div className="flex items-center gap-2">
                      {bookloreTestResult.success ? (
                        <CheckCircle className="h-4 w-4" />
                      ) : (
                        <XCircle className="h-4 w-4" />
                      )}
                      <span className="text-sm">
                        {bookloreTestResult.success
                          ? `Connected! Found ${bookloreTestResult.libraries?.length || 0} libraries`
                          : bookloreTestResult.error}
                      </span>
                    </div>
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-4 border-t border-border">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowBookloreModal(false);
                      resetBookloreForm();
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleSaveBookloreServer}
                    disabled={saveBookloreServerMutation.isPending}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {saveBookloreServerMutation.isPending ? 'Saving...' : editingBookloreServer ? 'Update' : 'Add Server'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* Readarr Settings */}
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-foreground">Readarr</CardTitle>
              <CardDescription>
                Configure your Readarr server(s) below. You can connect multiple Readarr servers (e.g., one for ebooks and one for audiobooks). Administrators are able to override the server used to process requests.
              </CardDescription>
            </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing servers */}
          {servers.map((server: ReadarrServer) => (
            <div
              key={server.id}
              className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/50"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-foreground">{server.name}</span>
                  {server.is_default && (
                    <Badge variant="secondary" className="text-xs">Default</Badge>
                  )}
                  {server.is_audiobook && (
                    <Badge variant="secondary" className="text-xs">Audiobook</Badge>
                  )}
                  {server.use_ssl && (
                    <Badge variant="secondary" className="text-xs">SSL</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {server.use_ssl ? 'https' : 'http'}://{server.hostname}:{server.port}
                  {server.url_base && `/${server.url_base}`}
                </p>
                {server.is_audiobook ? (
                  <p className="text-xs text-muted-foreground mt-1">
                    Audiobook Profile: {server.audiobook_quality_profile_id ? `ID ${server.audiobook_quality_profile_id}` : 'Not set'} • 
                    Root Folder: {server.audiobook_root_folder || 'Not set'}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground mt-1">
                    Ebook Profile: {server.ebook_quality_profile_id ? `ID ${server.ebook_quality_profile_id}` : 'Not set'} • 
                    Root Folder: {server.ebook_root_folder || 'Not set'}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleEditServer(server)}
                >
                  <Edit className="h-4 w-4 mr-1" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => deleteServerMutation.mutate(server.id)}
                  disabled={deleteServerMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}

          {/* Add new server button */}
          <button
            onClick={handleAddServer}
            className="w-full p-4 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-secondary/50 transition-colors flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-5 w-5" />
            Add New Readarr Server
          </button>
        </CardContent>
      </Card>

      {/* Add/Edit Server Modal */}
      <Dialog open={showServerModal} onOpenChange={setShowServerModal}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingServer ? 'Edit Readarr Server' : 'Add New Readarr Server'}
            </DialogTitle>
            <DialogDescription>
              Configure your Readarr server connection and settings
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            {/* Server Type */}
            <div className="space-y-3">
              <Label className="text-foreground">Server Type</Label>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="is-default"
                  checked={serverForm.is_default}
                  onCheckedChange={(checked) =>
                    setServerForm({ ...serverForm, is_default: checked === true })
                  }
                />
                <Label htmlFor="is-default" className="font-normal cursor-pointer">
                  Default Server
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="is-audiobook"
                  checked={serverForm.is_audiobook}
                  onCheckedChange={(checked) =>
                    setServerForm({ ...serverForm, is_audiobook: checked === true })
                  }
                />
                <Label htmlFor="is-audiobook" className="font-normal cursor-pointer">
                  Audiobook Server
                </Label>
              </div>
            </div>

            {/* Server Details */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="server-name" className="text-foreground">
                  Server Name *
                </Label>
                <Input
                  id="server-name"
                  value={serverForm.name}
                  onChange={(e) => setServerForm({ ...serverForm, name: e.target.value })}
                  placeholder="e.g., Ebooks"
                  className="bg-secondary border-border"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="hostname" className="text-foreground">
                  Hostname or IP Address *
                </Label>
                <Input
                  id="hostname"
                  value={serverForm.hostname}
                  onChange={(e) => setServerForm({ ...serverForm, hostname: e.target.value })}
                  placeholder="http://localhost"
                  className="bg-secondary border-border"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="port" className="text-foreground">
                  Port *
                </Label>
                <Input
                  id="port"
                  type="number"
                  value={serverForm.port}
                  onChange={(e) => setServerForm({ ...serverForm, port: parseInt(e.target.value) || 8787 })}
                  className="bg-secondary border-border"
                />
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="use-ssl"
                  checked={serverForm.use_ssl}
                  onCheckedChange={(checked) =>
                    setServerForm({ ...serverForm, use_ssl: checked === true })
                  }
                />
                <Label htmlFor="use-ssl" className="font-normal cursor-pointer">
                  Use SSL
                </Label>
              </div>

              <div className="space-y-2">
                <Label htmlFor="api-key" className="text-foreground">
                  API Key *
                </Label>
                <div className="relative">
                  <Input
                    id="api-key"
                    type={showApiKey ? "text" : "password"}
                    value={serverForm.api_key}
                    onChange={(e) => setServerForm({ ...serverForm, api_key: e.target.value })}
                    className="bg-secondary border-border pr-20"
                  />
                  <div className="absolute right-0 top-0 h-full flex items-center gap-1 pr-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setShowApiKey(!showApiKey)}
                    >
                      {showApiKey ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={handleTestConnection}
                      disabled={testingConnection}
                    >
                      <RefreshCw className={`h-4 w-4 ${testingConnection ? 'animate-spin' : ''}`} />
                    </Button>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="url-base" className="text-foreground">
                  URL Base
                </Label>
                <Input
                  id="url-base"
                  value={serverForm.url_base}
                  onChange={(e) => setServerForm({ ...serverForm, url_base: e.target.value })}
                  placeholder="Optional"
                  className="bg-secondary border-border"
                />
              </div>

              <Button
                type="button"
                variant="outline"
                onClick={handleTestConnection}
                disabled={testingConnection || !serverForm.hostname || !serverForm.api_key}
                className="w-full"
              >
                <TestTube className="h-4 w-4 mr-2" />
                {testingConnection ? 'Testing Connection...' : 'Test Connection'}
              </Button>
            </div>

            {/* Ebook Settings */}
            {!serverForm.is_audiobook && (
              <div className="space-y-4 border-t border-border pt-4">
                <h3 className="font-medium text-foreground">Ebook Settings</h3>
                
                <div className="space-y-2">
                  <Label htmlFor="ebook-quality-profile" className="text-foreground">
                    Quality Profile *
                  </Label>
                  <Select
                    value={serverForm.ebook_quality_profile_id?.toString() || ''}
                    onValueChange={(value) => {
                      const profileId = value ? parseInt(value, 10) : undefined;
                      setServerForm({ ...serverForm, ebook_quality_profile_id: isNaN(profileId as number) ? undefined : profileId });
                    }}
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select quality profile" : "Test connection to load quality profiles"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.quality_profiles?.map((profile) => (
                        <SelectItem key={profile.id} value={profile.id.toString()}>
                          {profile.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ebook-root-folder" className="text-foreground">
                    Root Folder *
                  </Label>
                  <Select
                    value={serverForm.ebook_root_folder || ''}
                    onValueChange={(value) =>
                      setServerForm({ ...serverForm, ebook_root_folder: value })
                    }
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select root folder" : "Test connection to load root folders"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.root_folders?.map((folder) => (
                        <SelectItem key={folder.path} value={folder.path}>
                          {folder.path}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ebook-tags" className="text-foreground">
                    Tags
                  </Label>
                  <Select
                    value={serverForm.ebook_tags || ''}
                    onValueChange={(value) =>
                      setServerForm({ ...serverForm, ebook_tags: value })
                    }
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select tags" : "Test connection to load tags"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.tags?.map((tag) => (
                        <SelectItem key={tag.id} value={tag.id.toString()}>
                          {tag.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Audiobook Settings */}
            {serverForm.is_audiobook && (
              <div className="space-y-4 border-t border-border pt-4">
                <h3 className="font-medium text-foreground">Audiobook Settings</h3>
                
                <div className="space-y-2">
                  <Label htmlFor="audiobook-quality-profile" className="text-foreground">
                    Audiobook Quality Profile
                  </Label>
                  <Select
                    value={serverForm.audiobook_quality_profile_id?.toString() || ''}
                    onValueChange={(value) => {
                      const profileId = value ? parseInt(value, 10) : undefined;
                      setServerForm({ ...serverForm, audiobook_quality_profile_id: isNaN(profileId as number) ? undefined : profileId });
                    }}
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select quality profile" : "Test connection to load quality profiles"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.quality_profiles?.map((profile) => (
                        <SelectItem key={profile.id} value={profile.id.toString()}>
                          {profile.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="audiobook-root-folder" className="text-foreground">
                    Audiobook Root Folder
                  </Label>
                  <Select
                    value={serverForm.audiobook_root_folder || ''}
                    onValueChange={(value) =>
                      setServerForm({ ...serverForm, audiobook_root_folder: value })
                    }
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select root folder" : "Test connection to load root folders"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.root_folders?.map((folder) => (
                        <SelectItem key={folder.path} value={folder.path}>
                          {folder.path}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="audiobook-tags" className="text-foreground">
                    Audiobook Tags
                  </Label>
                  <Select
                    value={serverForm.audiobook_tags || ''}
                    onValueChange={(value) =>
                      setServerForm({ ...serverForm, audiobook_tags: value })
                    }
                  >
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue placeholder={testResults ? "Select tags" : "Test connection to load tags"} />
                    </SelectTrigger>
                    <SelectContent>
                      {testResults?.tags?.map((tag) => (
                        <SelectItem key={tag.id} value={tag.id.toString()}>
                          {tag.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex justify-end gap-2 pt-4 border-t border-border">
              <Button
                variant="outline"
                onClick={() => {
                  setShowServerModal(false);
                  resetServerForm();
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSaveServer}
                disabled={saveServerMutation.isPending}
              >
                <Save className="h-4 w-4 mr-2" />
                {saveServerMutation.isPending ? 'Saving...' : editingServer ? 'Update Server' : 'Add Server'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
        </TabsContent>

        <TabsContent value="jobs" className="space-y-6 mt-6">
          <div>
            <h2 className="text-xl font-semibold text-foreground">Jobs & Cache</h2>
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
                {jobsLoading ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground">
                      Loading jobs...
                    </TableCell>
                  </TableRow>
                ) : jobsError ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-destructive">
                      Error loading jobs: {jobsError instanceof Error ? jobsError.message : 'Unknown error'}
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
                            <Countdown nextExecution={job.next_execution} />
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleEditJob(job)}
                              className="gap-2"
                            >
                              <Edit className="h-4 w-4" />
                              Edit
                            </Button>
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
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>

          {/* Edit Job Modal */}
          <Dialog open={showJobModal} onOpenChange={setShowJobModal}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Modify Job</DialogTitle>
                <DialogDescription>
                  Change the schedule for this job
                </DialogDescription>
              </DialogHeader>

              {editingJob && (
                <div className="space-y-4">
                  <div>
                    <Label className="text-muted-foreground text-sm">Job Name</Label>
                    <p className="text-foreground font-medium">{formatJobName(editingJob.name)}</p>
                  </div>

                  <div>
                    <Label className="text-muted-foreground text-sm">Current Frequency</Label>
                    <p className="text-foreground">{formatInterval(editingJob.interval_seconds)}</p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="job-frequency" className="text-foreground">
                      New Frequency
                    </Label>
                    <Select
                      value={selectedInterval.toString()}
                      onValueChange={(value) => setSelectedInterval(parseInt(value, 10))}
                    >
                      <SelectTrigger className="bg-secondary border-border">
                        <SelectValue placeholder="Select frequency" />
                      </SelectTrigger>
                      <SelectContent>
                        {intervalOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value.toString()}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex justify-end gap-2 pt-4 border-t border-border">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowJobModal(false);
                        setEditingJob(null);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleSaveJobSchedule}
                      disabled={updateJobMutation.isPending || selectedInterval === editingJob.interval_seconds}
                    >
                      <Save className="h-4 w-4 mr-2" />
                      {updateJobMutation.isPending ? 'Saving...' : 'Save Changes'}
                    </Button>
                  </div>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
}
