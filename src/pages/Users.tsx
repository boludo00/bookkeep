import { useState, useMemo } from 'react';
import { Users as UsersIcon, Plus, Edit, Trash2, Shield, User as UserIcon, Search, KeyRound, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '@/lib/api';

interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  is_admin: boolean;
  can_request_ebook?: boolean;
  can_request_audiobook?: boolean;
  can_request_physical?: boolean;
  can_download?: boolean;
  auto_approve_ebooks?: boolean;
  auto_approve_audiobooks?: boolean;
  auto_approve_physical?: boolean;
  total_requests?: number;
  created_at: string;
}

const PAGE_SIZE = 10;

export default function Users() {
  const queryClient = useQueryClient();
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [resetPassword, setResetPassword] = useState('');

  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
    is_admin: false,
    is_active: true,
    can_request_ebook: true,
    can_request_audiobook: true,
    can_download: true,
    auto_approve_ebooks: true,
    auto_approve_audiobooks: true,
  });

  const { data: users = [], isLoading, error } = useQuery<User[], Error>({
    queryKey: ['users', 'with-requests'],
    queryFn: () => usersApi.getAll(0, 1000),
  });

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        (u.full_name?.toLowerCase().includes(q) ?? false) ||
        String(u.id).includes(q),
    );
  }, [users, search]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE));
  const pagedUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const createUserMutation = useMutation({
    mutationFn: (userData: {
      email: string;
      username: string;
      password: string;
      full_name?: string;
      is_admin?: boolean;
    }) => usersApi.create(userData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User created successfully');
      setCreateDialogOpen(false);
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create user');
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ id, update }: { id: number; update: any }) =>
      usersApi.update(id, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User updated successfully');
      setEditDialogOpen(false);
      setSelectedUser(null);
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update user');
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      usersApi.resetPassword(id, password),
    onSuccess: () => {
      toast.success('Password reset successfully');
      setResetPassword('');
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to reset password');
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User deleted successfully');
      setDeleteDialogOpen(false);
      setSelectedUser(null);
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete user');
    },
  });

  const resetForm = () => {
    setFormData({
      email: '',
      username: '',
      password: '',
      full_name: '',
      is_admin: false,
      is_active: true,
      can_request_ebook: true,
      can_request_audiobook: true,
      can_download: true,
      auto_approve_ebooks: true,
      auto_approve_audiobooks: true,
    });
    setResetPassword('');
  };

  const handleCreate = () => {
    if (!formData.email || !formData.username || !formData.password) {
      toast.error('Please fill in all required fields');
      return;
    }
    createUserMutation.mutate({
      email: formData.email,
      username: formData.username,
      password: formData.password,
      full_name: formData.full_name || undefined,
      is_admin: formData.is_admin,
    });
  };

  const handleEdit = (user: User) => {
    setSelectedUser(user);
    setResetPassword('');
    setFormData({
      email: user.email,
      username: user.username,
      password: '',
      full_name: user.full_name || '',
      is_admin: user.is_admin,
      is_active: user.is_active,
      can_request_ebook: user.can_request_ebook ?? true,
      can_request_audiobook: user.can_request_audiobook ?? true,
      can_download: user.can_download ?? true,
      auto_approve_ebooks: user.auto_approve_ebooks ?? true,
      auto_approve_audiobooks: user.auto_approve_audiobooks ?? true,
    });
    setEditDialogOpen(true);
  };

  const handleUpdate = () => {
    if (!selectedUser) return;
    updateUserMutation.mutate({
      id: selectedUser.id,
      update: {
        email: formData.email,
        username: formData.username,
        full_name: formData.full_name || undefined,
        is_admin: formData.is_admin,
        is_active: formData.is_active,
        can_request_ebook: formData.can_request_ebook,
        can_request_audiobook: formData.can_request_audiobook,
        can_download: formData.can_download,
        auto_approve_ebooks: formData.auto_approve_ebooks,
        auto_approve_audiobooks: formData.auto_approve_audiobooks,
      },
    });
  };

  const handleResetPassword = () => {
    if (!selectedUser) return;
    if (resetPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    resetPasswordMutation.mutate({ id: selectedUser.id, password: resetPassword });
  };

  const handleDelete = (user: User) => {
    setSelectedUser(user);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (selectedUser) {
      deleteUserMutation.mutate(selectedUser.id);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Management</h1>
          <p className="text-muted-foreground mt-1">Manage users and their permissions</p>
        </div>
        <Button onClick={() => { resetForm(); setCreateDialogOpen(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Create User
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Total Users</p>
          <p className="text-3xl font-bold text-foreground mt-1">{users.length}</p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Admins</p>
          <p className="text-3xl font-bold text-primary mt-1">
            {users.filter((u) => u.is_admin).length}
          </p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Active Users</p>
          <p className="text-3xl font-bold text-success mt-1">
            {users.filter((u) => u.is_active).length}
          </p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Total Requests</p>
          <p className="text-3xl font-bold text-foreground mt-1">
            {users.reduce((sum, u) => sum + (u.total_requests || 0), 0)}
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search by name, email, or ID…"
          className="pl-9 bg-card border-border"
        />
      </div>

      {/* Users Table */}
      <div className="rounded-lg border border-border overflow-hidden">
        {isLoading ? (
          <div className="text-center py-12 text-muted-foreground">Loading users…</div>
        ) : error ? (
          <div className="text-center py-12">
            <div className="text-destructive mb-2 font-medium">Failed to load users</div>
            <div className="text-sm text-muted-foreground">
              {(error as any)?.message || 'Please check your connection and try again'}
            </div>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            {search ? 'No users match your search' : 'No users found'}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-secondary/50 hover:bg-secondary/50">
                <TableHead className="text-muted-foreground w-12">ID</TableHead>
                <TableHead className="text-muted-foreground">User</TableHead>
                <TableHead className="text-muted-foreground">Email</TableHead>
                <TableHead className="text-muted-foreground">Role</TableHead>
                <TableHead className="text-muted-foreground">Requests</TableHead>
                <TableHead className="text-muted-foreground">Auto-Approve</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-right text-muted-foreground">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pagedUsers.map((user) => (
                <TableRow key={user.id} className="bg-card hover:bg-muted/50">
                  <TableCell className="text-muted-foreground font-mono text-sm">
                    {user.id}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                        {user.is_admin ? (
                          <Shield className="h-5 w-5 text-primary" />
                        ) : (
                          <UserIcon className="h-5 w-5 text-muted-foreground" />
                        )}
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{user.username}</p>
                        {user.full_name && (
                          <p className="text-sm text-muted-foreground">{user.full_name}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-foreground">{user.email}</TableCell>
                  <TableCell>
                    {user.is_admin ? (
                      <Badge variant="outline" className="border-primary text-primary">
                        <Shield className="h-3 w-3 mr-1" />
                        Admin
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-border">User</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-foreground">{user.total_requests || 0}</TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      {user.auto_approve_ebooks && (
                        <Badge variant="outline" className="text-xs border-success text-success w-fit">
                          Ebooks
                        </Badge>
                      )}
                      {user.auto_approve_audiobooks && (
                        <Badge variant="outline" className="text-xs border-success text-success w-fit">
                          Audiobooks
                        </Badge>
                      )}
                      {!user.auto_approve_ebooks && !user.auto_approve_audiobooks && (
                        <span className="text-xs text-muted-foreground">None</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {user.is_active ? (
                      <Badge variant="outline" className="border-success text-success">Active</Badge>
                    ) : (
                      <Badge variant="outline" className="border-destructive text-destructive">Inactive</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={() => handleEdit(user)}>
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => handleDelete(user)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filteredUsers.length)} of {filteredUsers.length} users
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span>
              Page {page} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Create User Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="bg-card border-border max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">Create New User</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Add a new user to the system
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label className="text-foreground">Email *</Label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="user@example.com"
                className="bg-secondary border-border"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground">Username *</Label>
              <Input
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                placeholder="username"
                className="bg-secondary border-border"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground">Password *</Label>
              <Input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="••••••••"
                className="bg-secondary border-border"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground">Full Name</Label>
              <Input
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                placeholder="John Doe"
                className="bg-secondary border-border"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="create-admin"
                checked={formData.is_admin}
                onCheckedChange={(checked) => setFormData({ ...formData, is_admin: !!checked })}
              />
              <Label htmlFor="create-admin" className="text-foreground cursor-pointer">
                Admin User
              </Label>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={createUserMutation.isPending}>
              Create User
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={(open) => { setEditDialogOpen(open); if (!open) setResetPassword(''); }}>
        <DialogContent className="bg-card border-border max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              Edit User
              {selectedUser && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  ID: {selectedUser.id}
                </span>
              )}
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Update user information and permissions
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label className="text-foreground">Email *</Label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="bg-secondary border-border"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground">Username *</Label>
              <Input
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                className="bg-secondary border-border"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground">Full Name</Label>
              <Input
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="bg-secondary border-border"
              />
            </div>

            <div className="space-y-4 pt-4 border-t border-border">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-foreground">Active</Label>
                  <p className="text-sm text-muted-foreground">User account is active</p>
                </div>
                <Switch
                  checked={formData.is_active}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-foreground">Admin</Label>
                  <p className="text-sm text-muted-foreground">Grant admin privileges</p>
                </div>
                <Switch
                  checked={formData.is_admin}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_admin: checked })}
                />
              </div>
            </div>

            <div className="space-y-4 pt-4 border-t border-border">
              <h3 className="text-sm font-semibold text-foreground">Request Permissions</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Can Request Ebooks</Label>
                    <p className="text-sm text-muted-foreground">Allow user to request ebooks</p>
                  </div>
                  <Switch
                    checked={formData.can_request_ebook}
                    onCheckedChange={(checked) => setFormData({ ...formData, can_request_ebook: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Can Request Audiobooks</Label>
                    <p className="text-sm text-muted-foreground">Allow user to request audiobooks</p>
                  </div>
                  <Switch
                    checked={formData.can_request_audiobook}
                    onCheckedChange={(checked) => setFormData({ ...formData, can_request_audiobook: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Can Download</Label>
                    <p className="text-sm text-muted-foreground">Allow user to search indexers and download books</p>
                  </div>
                  <Switch
                    checked={formData.can_download}
                    onCheckedChange={(checked) => setFormData({ ...formData, can_download: checked })}
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4 pt-4 border-t border-border">
              <h3 className="text-sm font-semibold text-foreground">Auto-Approve Permissions</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Auto-Approve Ebooks</Label>
                    <p className="text-sm text-muted-foreground">Automatically approve ebook requests</p>
                  </div>
                  <Switch
                    checked={formData.auto_approve_ebooks}
                    onCheckedChange={(checked) => setFormData({ ...formData, auto_approve_ebooks: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-foreground">Auto-Approve Audiobooks</Label>
                    <p className="text-sm text-muted-foreground">Automatically approve audiobook requests</p>
                  </div>
                  <Switch
                    checked={formData.auto_approve_audiobooks}
                    onCheckedChange={(checked) => setFormData({ ...formData, auto_approve_audiobooks: checked })}
                  />
                </div>
              </div>
            </div>

            {/* Password Reset */}
            <div className="space-y-3 pt-4 border-t border-border">
              <div>
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <KeyRound className="h-4 w-4" />
                  Reset Password
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Set a new password for this user without requiring their current one.
                </p>
              </div>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="New password (min. 8 characters)"
                  className="bg-secondary border-border"
                />
                <Button
                  variant="outline"
                  onClick={handleResetPassword}
                  disabled={resetPassword.length < 8 || resetPasswordMutation.isPending}
                >
                  Reset
                </Button>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleUpdate} disabled={updateUserMutation.isPending}>
              Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="bg-card border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">Delete User</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">
              Are you sure you want to delete <strong>{selectedUser?.username}</strong>?{' '}
              This action cannot be undone. All their requests will remain but will be orphaned.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
