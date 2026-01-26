import { NavLink, useLocation, Link } from 'react-router-dom';
import { Compass, Clock, Settings, Users, Shield, BookOpen, Download, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUser } from '@/contexts/UserContext';
import { useQuery } from '@tanstack/react-query';
import { requestsApi } from '@/lib/api';

const navItems = [
  { to: '/', icon: Compass, label: 'Discover' },
  { to: '/requests', icon: Clock, label: 'Requests' },
  { to: '/downloads', icon: Download, label: 'Downloads' },
  { to: '/series', icon: BookOpen, label: 'Series' },
];

const adminItems = [
  { to: '/admin', icon: Shield, label: 'Admin' },
  { to: '/admin/users', icon: Users, label: 'Users' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

interface SidebarProps {
  variant?: 'desktop' | 'mobile';
  className?: string;
}

export function Sidebar({ variant = 'desktop', className }: SidebarProps) {
  const location = useLocation();
  const { isAdmin } = useUser();

  const { data: pendingRequests } = useQuery({
    queryKey: ['requests', 'pending-count'],
    queryFn: () => requestsApi.getAll(0, 100, 'pending'),
    enabled: isAdmin,
    refetchInterval: 60_000,
  });
  const pendingCount = pendingRequests?.length ?? 0;

  const appVersion = import.meta.env.VITE_APP_VERSION || 'dev';
  const isMobile = variant === 'mobile';

  return (
    <aside
      className={cn(
        'bg-sidebar-background flex flex-col relative overflow-hidden',
        isMobile
          ? 'h-full w-full border-r-0'
          : 'fixed left-0 top-0 z-40 h-screen w-64 border-r border-sidebar-border',
        className
      )}
    >
      {/* Ambient glow effect */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[200%] h-32 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

      {/* Logo */}
      <div className="relative flex items-center gap-3 px-6 py-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20">
          <Sparkles className="h-5 w-5 text-primary" />
        </div>
        <Link
          to="/"
          className="text-2xl font-bold tracking-tight text-sidebar-foreground hover:text-primary transition-colors duration-300"
        >
          Bookkeep
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2">
        <div className="space-y-1">
          {navItems.map((item, index) => {
            const isActive = location.pathname === item.to;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={cn(
                  'group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300',
                  isActive
                    ? 'bg-primary/15 text-primary shadow-sm'
                    : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground'
                )}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-300',
                  isActive
                    ? 'bg-primary/20'
                    : 'bg-transparent group-hover:bg-sidebar-accent'
                )}>
                  <item.icon className={cn(
                    'h-4 w-4 transition-transform duration-300',
                    isActive && 'scale-110'
                  )} />
                </div>
                <span className="tracking-wide">{item.label}</span>
                {isActive && (
                  <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                )}
              </NavLink>
            );
          })}
        </div>

        {/* Admin Section */}
        {isAdmin && (
          <div className="mt-10">
            <div className="flex items-center gap-2 px-4 mb-3">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-sidebar-border to-transparent" />
              <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-sidebar-muted/60">
                Admin
              </span>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-sidebar-border to-transparent" />
            </div>
            <div className="space-y-1">
              {adminItems.map((item) => {
                const isExactMatch = location.pathname === item.to;
                const isChildPath = location.pathname.startsWith(item.to + '/');
                const isActive = item.to === '/admin'
                  ? isExactMatch
                  : (isExactMatch || isChildPath);
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={cn(
                      'group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300',
                      isActive
                        ? 'bg-primary/15 text-primary shadow-sm'
                        : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground'
                    )}
                  >
                    <div className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-300',
                      isActive
                        ? 'bg-primary/20'
                        : 'bg-transparent group-hover:bg-sidebar-accent'
                    )}>
                      <item.icon className={cn(
                        'h-4 w-4 transition-transform duration-300',
                        isActive && 'scale-110'
                      )} />
                    </div>
                    <span className="tracking-wide">{item.label}</span>
                    {item.to === '/admin' && pendingCount > 0 ? (
                      <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-warning px-1.5 text-[10px] font-bold text-warning-foreground">
                        {pendingCount}
                      </span>
                    ) : isActive ? (
                      <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                    ) : null}
                  </NavLink>
                );
              })}
            </div>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className={cn(
        'relative border-t border-sidebar-border/50 px-6 py-5',
        isMobile && 'mt-auto'
      )}>
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
          <p className="text-sm font-semibold text-sidebar-foreground/80 tracking-wide">
            Bookkeep <span className="text-primary">{appVersion}</span>
          </p>
        </div>
      </div>
    </aside>
  );
}
