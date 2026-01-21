import { NavLink, useLocation, Link } from 'react-router-dom';
import { Compass, Clock, Settings, Users, Shield, BookOpen, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUser } from '@/contexts/UserContext';

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
  
  const appVersion = import.meta.env.VITE_APP_VERSION || 'dev';
  const isMobile = variant === 'mobile';

  return (
    <aside
      className={cn(
        'bg-sidebar-background border-sidebar-border flex flex-col',
        isMobile
          ? 'h-full w-full border-r-0'
          : 'fixed left-0 top-0 z-40 h-screen w-64 border-r',
        className
      )}
    >
      {/* Logo */}
      <div className="flex items-center px-6 py-6">
        <Link
          to="/"
          className="text-2xl font-bold text-sidebar-foreground hover:text-sidebar-primary transition-colors"
        >
          Bookkeep
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.to;
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-sidebar-primary text-sidebar-primary-foreground'
                      : 'text-sidebar-muted hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {item.label}
                </NavLink>
              </li>
            );
          })}
        </ul>

        {/* Admin Section - Only visible to admins */}
        {isAdmin && (
          <div className="mt-8">
            <p className="mb-2 px-4 text-xs font-semibold uppercase tracking-wider text-sidebar-muted">
              Admin
            </p>
            <ul className="space-y-1">
              {adminItems.map((item) => {
                // For exact matches, use exact match
                // For parent routes like /admin, only match if pathname is exactly /admin
                // For child routes like /admin/users, match if pathname starts with /admin/users
                const isExactMatch = location.pathname === item.to;
                const isChildPath = location.pathname.startsWith(item.to + '/');
                // Special case: /admin should only match exactly, not /admin/users
                const isActive = item.to === '/admin' 
                  ? isExactMatch 
                  : (isExactMatch || isChildPath);
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      className={cn(
                        'flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-sidebar-primary text-sidebar-primary-foreground'
                          : 'text-sidebar-muted hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
                      )}
                    >
                      <item.icon className="h-5 w-5" />
                      {item.label}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className={cn('border-t border-sidebar-border px-4 py-4', isMobile && 'mt-auto')}>
        <p className="text-xs text-sidebar-muted">
          Bookkeep {appVersion}
        </p>
      </div>
    </aside>
  );
}
