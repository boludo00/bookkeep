import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Eye, EyeOff, AlertTriangle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import { checkBackendAvailable, usersApi, authApi } from '@/lib/api';
import { BookkeepLogo } from '@/components/brand/BookkeepLogo';

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [backendChecked, setBackendChecked] = useState(false);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  useEffect(() => {
    checkBackendAvailable().then((available) => {
      setBackendUp(available);
      setBackendChecked(true);
    });
  }, []);

  const { data: adminCheck, isLoading: checkingAdmin } = useQuery({
    queryKey: ['admin-exists'],
    queryFn: () => usersApi.checkAdminExists(),
    retry: false,
    enabled: backendChecked,
  });

  useEffect(() => {
    if (backendChecked && !checkingAdmin && adminCheck && !adminCheck.admin_exists) {
      navigate('/admin-setup', { replace: true });
    }
  }, [backendChecked, checkingAdmin, adminCheck, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!username.trim() || !password) {
      toast.error('Please enter username and password');
      return;
    }

    setIsLoading(true);

    try {
      if (!backendUp) {
        toast.error('Backend unavailable', {
          description: 'Start the backend service and try again.',
        });
        return;
      }

      await authApi.login(username, password);

      toast.success('Welcome back!', {
        description: `Logged in as ${username}`,
      });

      navigate('/');
      window.location.reload();
    } catch (error: any) {
      toast.error('Login failed', {
        description: error.message || 'Please check your credentials and try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (!backendChecked || (backendUp && checkingAdmin)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
            <Loader2 className="relative h-10 w-10 animate-spin text-primary" />
          </div>
          <p className="text-muted-foreground font-medium">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 relative overflow-hidden">
      {/* Cinematic background effects */}
      <div className="fixed inset-0 pointer-events-none">
        {/* Emerald glow top-left */}
        <div className="absolute -top-40 -left-40 w-[500px] h-[500px] bg-primary/10 rounded-full blur-[150px]" />
        {/* Amber glow bottom-right */}
        <div className="absolute -bottom-40 -right-40 w-[400px] h-[400px] bg-amber-500/10 rounded-full blur-[120px]" />
        {/* Center gradient */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-radial from-primary/5 to-transparent rounded-full" />
      </div>

      <Card className="relative w-full max-w-md bg-card/50 backdrop-blur-xl border-border/50 shadow-2xl rounded-2xl animate-fade-in-up">
        <CardHeader className="text-center space-y-6 pb-4">
          {/* Logo */}
          <div className="flex justify-center">
            <div className="relative">
              {/* Glow effect */}
              <div className="absolute inset-0 bg-primary/20 rounded-2xl blur-xl" />
              <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20">
                <BookkeepLogo className="h-12 w-12" />
              </div>
            </div>
          </div>
          <div className="space-y-2">
            <CardTitle className="text-3xl font-bold tracking-tight">
              Welcome back
            </CardTitle>
            <CardDescription className="text-base text-muted-foreground">
              Sign in to continue to Bookkeep
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-6 pt-2">
          {/* Backend unavailable alert */}
          {!backendUp && (
            <Alert className="bg-amber-500/10 border-amber-500/30 rounded-xl">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              <AlertDescription className="text-amber-400">
                Backend server unavailable. Start the backend service and refresh this page.
              </AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-sm font-medium">
                Username
              </Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                className="h-12 bg-muted/30 border-border/50 rounded-xl placeholder:text-muted-foreground/50 focus:bg-muted/50 focus:border-primary/30 transition-all duration-300"
                disabled={!backendUp}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-medium">
                Password
              </Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="h-12 bg-muted/30 border-border/50 rounded-xl pr-12 placeholder:text-muted-foreground/50 focus:bg-muted/50 focus:border-primary/30 transition-all duration-300"
                  disabled={!backendUp}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors duration-300"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-12 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium shadow-lg shadow-primary/25 hover:shadow-primary/40 transition-all duration-300"
              disabled={isLoading || !backendUp}
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Signing in...
                </>
              ) : backendUp ? (
                'Sign In'
              ) : (
                'Backend Offline'
              )}
            </Button>
          </form>

          {/* Footer */}
          <div className="pt-4 text-center">
            <p className="text-xs text-muted-foreground/60">
              Your personal library companion
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
