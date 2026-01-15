import { useQuery } from '@tanstack/react-query';
import { Navigate, Outlet } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { usersApi } from '@/lib/api';

export function AdminCheckWrapper() {
  const { data: adminCheck, isLoading } = useQuery({
    queryKey: ['admin-exists'],
    queryFn: () => usersApi.checkAdminExists(),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // If no admin exists (and backend is up), redirect to setup page
  // Mock mode always returns admin_exists: true
  if (!adminCheck?.admin_exists) {
    return <Navigate to="/admin-setup" replace />;
  }

  return <Outlet />;
}
