import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Calendar, Hash, Clock, CheckCircle, XCircle, Loader2, Eye, EyeOff, KeyRound, RefreshCw, BookMarked } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { useUser } from '@/contexts/UserContext';
import { usersApi, requestsApi, hardcoverSyncApi } from '@/lib/api';
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

  // Hardcover Sync state
  const [hardcoverToken, setHardcoverToken] = useState('');
  const [showHardcoverToken, setShowHardcoverToken] = useState(false);

  const { data: syncConfig, isLoading: syncConfigLoading } = useQuery({
    queryKey: ['hardcoverSyncConfig'],
    queryFn: () => hardcoverSyncApi.getConfig(),
    enabled: !!user,
  });

  const { data: hardcoverLists = [], isLoading: listsLoading } = useQuery({
    queryKey: ['hardcoverLists'],
    queryFn: () => hardcoverSyncApi.getLists(),
    enabled: !!syncConfig?.has_token,
    retry: false,
  });

  const updateSyncMutation = useMutation({
    mutationFn: hardcoverSyncApi.updateConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hardcoverSyncConfig'] });
      queryClient.invalidateQueries({ queryKey: ['hardcoverLists'] });
    },
    onError: (error: any) => {
      toast.error('Failed to update Hardcover sync', { description: error.message });
    },
  });

  const runSyncMutation = useMutation({
    mutationFn: hardcoverSyncApi.runSync,
    onSuccess: (data) => {
      toast.success('Sync started', { description: data.message });
      queryClient.invalidateQueries({ queryKey: ['hardcoverSyncConfig'] });
    },
    onError: (error: any) => {
      toast.error('Sync failed', { description: error.message });
    },
  });

  const handleSaveToken = () => {
    if (!hardcoverToken.trim()) return;
    updateSyncMutation.mutate(
      { hardcover_api_token: hardcoverToken.trim() },
      { onSuccess: () => { toast.success('API token saved'); setHardcoverToken(''); } }
    );
  };

  const handleClearToken = () => {
    updateSyncMutation.mutate(
      { clear_token: true, is_enabled: false },
      { onSuccess: () => toast.success('API token removed') }
    );
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

      {/* Hardcover List Sync */}
      <Card className="bg-card/50 border-border">
        <CardHeader>
          <div className="flex items-center gap-2">
            <BookMarked className="h-5 w-5 text-primary" />
            <CardTitle>Hardcover List Sync</CardTitle>
          </div>
          <CardDescription>
            Automatically request books from your Hardcover to-read list or custom lists.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {syncConfigLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* API Token */}
              <div className="space-y-2">
                <Label>Hardcover API Token</Label>
                {syncConfig?.using_app_token ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <CheckCircle className="h-4 w-4 text-emerald-500" />
                      Using the app-wide Hardcover token
                    </div>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <Input
                          type={showHardcoverToken ? 'text' : 'password'}
                          placeholder="Override with your own token (optional)"
                          value={hardcoverToken}
                          onChange={(e) => setHardcoverToken(e.target.value)}
                          className="pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowHardcoverToken(!showHardcoverToken)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          {showHardcoverToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                      <Button
                        onClick={handleSaveToken}
                        disabled={!hardcoverToken.trim() || updateSyncMutation.isPending}
                        variant="outline"
                      >
                        Save
                      </Button>
                    </div>
                  </div>
                ) : syncConfig?.has_personal_token ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground flex-1">Personal token configured</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleClearToken}
                      disabled={updateSyncMutation.isPending}
                    >
                      Remove
                    </Button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Input
                        type={showHardcoverToken ? 'text' : 'password'}
                        placeholder="Paste your Hardcover API token"
                        value={hardcoverToken}
                        onChange={(e) => setHardcoverToken(e.target.value)}
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowHardcoverToken(!showHardcoverToken)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showHardcoverToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    <Button
                      onClick={handleSaveToken}
                      disabled={!hardcoverToken.trim() || updateSyncMutation.isPending}
                    >
                      Save
                    </Button>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  The app-wide token is used by default. Set a personal token to sync your own Hardcover account.
                </p>
              </div>

              {syncConfig?.has_token && (
                <>
                  <Separator />

                  {/* Enable toggle */}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label>Enable Sync</Label>
                      <p className="text-sm text-muted-foreground">Automatically request books on schedule</p>
                    </div>
                    <Switch
                      checked={syncConfig.is_enabled}
                      onCheckedChange={(checked) =>
                        updateSyncMutation.mutate({ is_enabled: checked })
                      }
                      disabled={updateSyncMutation.isPending}
                    />
                  </div>

                  {/* Sync to-read */}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label>Sync "Want to Read"</Label>
                      <p className="text-sm text-muted-foreground">Request books from your to-read status</p>
                    </div>
                    <Switch
                      checked={syncConfig.sync_to_read}
                      onCheckedChange={(checked) =>
                        updateSyncMutation.mutate({ sync_to_read: checked })
                      }
                      disabled={updateSyncMutation.isPending}
                    />
                  </div>

                  {/* Default format */}
                  <div className="space-y-2">
                    <Label>Default Format</Label>
                    <Select
                      value={syncConfig.default_format}
                      onValueChange={(value) =>
                        updateSyncMutation.mutate({ default_format: value })
                      }
                      disabled={updateSyncMutation.isPending}
                    >
                      <SelectTrigger className="w-48">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ebook">Ebook</SelectItem>
                        <SelectItem value="audiobook">Audiobook</SelectItem>
                        <SelectItem value="both">Both</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Custom lists */}
                  <div className="space-y-2">
                    <Label>Custom Lists</Label>
                    <p className="text-sm text-muted-foreground">Also sync books from these lists</p>
                    {listsLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Loading lists…
                      </div>
                    ) : hardcoverLists.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No custom lists found on your Hardcover account.</p>
                    ) : (
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {hardcoverLists.map((list) => (
                          <div key={list.id} className="flex items-center gap-2">
                            <Checkbox
                              id={`list-${list.id}`}
                              checked={syncConfig.sync_list_ids.includes(list.id)}
                              onCheckedChange={(checked) => {
                                const updated = checked
                                  ? [...syncConfig.sync_list_ids, list.id]
                                  : syncConfig.sync_list_ids.filter((id) => id !== list.id);
                                updateSyncMutation.mutate({ sync_list_ids: updated });
                              }}
                              disabled={updateSyncMutation.isPending}
                            />
                            <label htmlFor={`list-${list.id}`} className="text-sm cursor-pointer">
                              {list.name}
                            </label>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <Separator />

                  {/* Status & manual sync */}
                  <div className="flex items-center justify-between">
                    <div>
                      {syncConfig.last_synced_at ? (
                        <p className="text-sm text-muted-foreground">
                          Last synced: {new Date(syncConfig.last_synced_at).toLocaleString()}
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground">Never synced</p>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => runSyncMutation.mutate()}
                      disabled={!syncConfig.is_enabled || runSyncMutation.isPending}
                      className="gap-2"
                    >
                      {runSyncMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      Sync Now
                    </Button>
                  </div>
                </>
              )}
            </>
          )}
        </CardContent>
      </Card>

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

