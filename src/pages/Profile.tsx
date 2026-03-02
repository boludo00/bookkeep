import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Calendar, Hash, Clock, CheckCircle, XCircle, Loader2, Eye, EyeOff, KeyRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';
import { usersApi, requestsApi } from '@/lib/api';
import type { BookRequest } from '@/types/book';

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { 
    month: 'long', 
    day: 'numeric', 
    year: 'numeric' 
  });
}

function getInitials(name: string | undefined, username: string): string {
  if (name && name.trim()) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  }
  return username.slice(0, 2).toUpperCase();
}

function getAvatarColor(username: string): string {
  const colors = [
    'bg-amber-500',
    'bg-rose-500',
    'bg-emerald-500',
    'bg-blue-500',
    'bg-purple-500',
    'bg-cyan-500',
    'bg-pink-500',
    'bg-orange-500',
  ];
  const hash = username.split('').reduce((a, b) => a + b.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

export default function Profile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, isAdmin, isLoading: userLoading } = useUser();
  
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);

  // Fetch user's requests
  const { data: requests = [], isLoading: requestsLoading } = useQuery({
    queryKey: ['userRequests', user?.id],
    queryFn: () => requestsApi.getAll(),
    enabled: !!user,
  });

  // Filter requests for current user
  const userRequests = requests.filter((r: any) => r.user_id === user?.id);
  const recentRequests = userRequests.slice(0, 10);

  // Password change mutation
  const passwordMutation = useMutation({
    mutationFn: () => usersApi.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      toast.success('Password changed successfully');
      setShowPasswordDialog(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    },
    onError: (error: any) => {
      toast.error('Failed to change password', {
        description: error.message || 'Please check your current password and try again.',
      });
    },
  });

  const handlePasswordChange = () => {
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    if (newPassword.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    passwordMutation.mutate();
  };

  if (userLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h1 className="text-2xl font-bold mb-4">Not logged in</h1>
        <p className="text-muted-foreground">Please log in to view your profile.</p>
      </div>
    );
  }

  const avatarColor = getAvatarColor(user.username);

  return (
    <div className="space-y-8">
      {/* Profile Header */}
      <div className="relative">
        {/* Background gradient */}
        <div className="absolute inset-0 h-32 bg-gradient-to-r from-primary/20 via-primary/10 to-transparent rounded-xl" />
        
        <div className="relative pt-8 pb-4 px-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <Avatar className={`h-24 w-24 border-4 border-background shadow-xl ${avatarColor}`}>
              <AvatarFallback className="text-2xl font-bold text-white bg-transparent">
                {getInitials(user.full_name, user.username)}
              </AvatarFallback>
            </Avatar>
            
            {/* User Info */}
            <div className="flex-1 pt-2">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-foreground">{user.username}</h1>
                {isAdmin && (
                  <Badge variant="secondary" className="bg-amber-500/20 text-amber-400 border-amber-500/30">
                    Admin
                  </Badge>
                )}
              </div>
              <p className="text-muted-foreground">{user.email}</p>
              <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  Joined {formatDate(user.created_at)}
                </span>
                <span className="flex items-center gap-1">
                  <Hash className="h-4 w-4" />
                  User ID: {user.id}
                </span>
              </div>
            </div>

            {/* Edit Settings Button */}
            {user?.has_password !== false && (
              <Button
                variant="outline"
                className="gap-2"
                onClick={() => setShowPasswordDialog(true)}
              >
                <KeyRound className="h-4 w-4" />
                Change Password
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-card/50 border-border">
          <CardHeader className="pb-2">
            <CardDescription>Total Requests</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{userRequests.length}</p>
          </CardContent>
        </Card>
        
        <Card className="bg-card/50 border-border">
          <CardHeader className="pb-2">
            <CardDescription>Ebook Requests</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {user.can_request_ebook ? 'Unlimited' : 'Disabled'}
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-card/50 border-border">
          <CardHeader className="pb-2">
            <CardDescription>Audiobook Requests</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {user.can_request_audiobook ? 'Unlimited' : 'Disabled'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Requests */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Recent Requests</h2>
          <Button variant="ghost" size="sm" onClick={() => navigate('/requests')}>
            View All →
          </Button>
        </div>
        
        {requestsLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : recentRequests.length === 0 ? (
          <Card className="bg-card/50 border-border">
            <CardContent className="py-8 text-center text-muted-foreground">
              No requests yet. Start browsing and request some books!
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {recentRequests.map((request: any) => (
              <div
                key={request.id}
                className="group relative rounded-lg overflow-hidden cursor-pointer card-hover"
                onClick={() => navigate(`/book/${request.book?.hardcover_id || request.book_id}`)}
              >
                {/* Cover */}
                <div className="aspect-[2/3] bg-card">
                  <img
                    src={request.book?.cover_url || '/placeholder.svg'}
                    alt={request.book?.title || 'Book'}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                </div>
                
                {/* Overlay with info */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent p-3 flex flex-col justify-end">
                  <p className="text-xs text-white/70">
                    {request.book?.published_date?.slice(0, 4) || 'Unknown'}
                  </p>
                  <h3 className="text-sm font-semibold text-white line-clamp-2">
                    {request.book?.title || 'Unknown Book'}
                  </h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-white/70">Status</span>
                    <Badge
                      variant="secondary"
                      className={
                        request.status === 'available'
                          ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                          : request.status === 'processing'
                          ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                          : request.status === 'denied'
                          ? 'bg-red-500/20 text-red-400 border-red-500/30'
                          : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                      }
                    >
                      {request.status.charAt(0).toUpperCase() + request.status.slice(1)}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Password Change Dialog */}
      <Dialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>Change Password</DialogTitle>
            <DialogDescription>
              Enter your current password and a new password.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="currentPassword">Current Password</Label>
              <div className="relative">
                <Input
                  id="currentPassword"
                  type={showCurrentPassword ? 'text' : 'password'}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showCurrentPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="newPassword">New Password</Label>
              <div className="relative">
                <Input
                  id="newPassword"
                  type={showNewPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm New Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPasswordDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handlePasswordChange}
              disabled={passwordMutation.isPending || !currentPassword || !newPassword || !confirmPassword}
            >
              {passwordMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Changing...
                </>
              ) : (
                'Change Password'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

