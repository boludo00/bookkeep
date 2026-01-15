import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import { checkBackendAvailable, usersApi } from '@/lib/api';
import { BookkeepLogo } from '@/components/brand/BookkeepLogo';

// Simple login API call
async function loginUser(username: string, password: string): Promise<{ user_id: number; is_admin: boolean }> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(error.detail || 'Invalid username or password');
  }
  
  return response.json();
}

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [backendChecked, setBackendChecked] = useState(false);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  
  // Check backend availability on mount
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
      // If backend is down, just log in with mock user
      if (!backendUp) {
        localStorage.setItem('userId', '1');
        toast.success('Welcome!', {
          description: 'Using mock data (backend unavailable)',
        });
        navigate('/');
        window.location.reload();
        return;
      }
      
      const result = await loginUser(username, password);
      
      // Store user ID in localStorage
      localStorage.setItem('userId', String(result.user_id));
      
      toast.success('Welcome back!', {
        description: `Logged in as ${username}`,
      });
      
      // Redirect to home
      navigate('/');
      
      // Force a page reload to refresh user context
      window.location.reload();
    } catch (error: any) {
      toast.error('Login failed', {
        description: error.message || 'Please check your credentials and try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-login when backend is down for seamless development
  const handleMockLogin = () => {
    localStorage.setItem('userId', '1');
    toast.success('Mock mode enabled', {
      description: 'Using sample data for UI development',
    });
    navigate('/');
    window.location.reload();
  };

  if (!backendChecked || (backendUp && checkingAdmin)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      {/* Background gradient */}
      <div className="fixed inset-0 bg-gradient-to-br from-primary/10 via-background to-background" />
      
      <Card className="relative w-full max-w-md bg-card/80 backdrop-blur-xl border-border shadow-2xl">
        <CardHeader className="text-center space-y-4">
          {/* Logo */}
          <div className="flex justify-center">
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl">
              <BookkeepLogo className="h-14 w-14" />
            </div>
          </div>
          <div>
            <CardTitle className="text-2xl font-bold">Welcome to Bookkeep</CardTitle>
            <CardDescription className="mt-2">
              Sign in to your account to continue
            </CardDescription>
          </div>
        </CardHeader>
        
        <CardContent className="space-y-4">
          {/* Backend unavailable info */}
          {!backendUp && (
            <Alert className="bg-muted/50 border-border">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Backend server unavailable. You can continue with mock data for UI development.
              </AlertDescription>
            </Alert>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                className="bg-background/50"
                disabled={!backendUp}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="bg-background/50 pr-10"
                  disabled={!backendUp}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            
            {backendUp ? (
              <Button 
                type="submit" 
                className="w-full" 
                size="lg"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  'Sign In'
                )}
              </Button>
            ) : (
              <Button 
                type="button"
                className="w-full" 
                size="lg"
                onClick={handleMockLogin}
              >
                Continue with Mock Data
              </Button>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
