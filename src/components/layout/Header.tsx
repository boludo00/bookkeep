import { useEffect, useState } from 'react';
import { Search, User, Settings, Clock, LogOut, Menu } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { SearchResults } from '@/components/search/SearchResults';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useQuery } from '@tanstack/react-query';
import { hardcoverApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import { useUser } from '@/contexts/UserContext';
import type { Book } from '@/types/book';

function getInitials(name: string | undefined, username: string): string {
  if (name && name.trim()) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  }
  return username?.slice(0, 2).toUpperCase() || 'U';
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
  const hash = (username || '').split('').reduce((a, b) => a + b.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useUser();

  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setDebouncedQuery('');
      return;
    }
    const timer = setTimeout(() => setDebouncedQuery(trimmed), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const { data: searchData, isFetching: isSearching, isFetched } = useQuery({
    queryKey: ['search-suggest', debouncedQuery],
    queryFn: () => hardcoverApi.searchGrouped(debouncedQuery, 5, { cacheOnly: true }),
    enabled: debouncedQuery.length > 1,
  });

  const groupedResults = {
    series: searchData?.series || [],
    authors: searchData?.authors || [],
    books: searchData?.books ? searchData.books.map(transformHardcoverBook) : [],
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setShowResults(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch(e);
    }
  };

  const avatarColor = user ? getAvatarColor(user.username) : 'bg-secondary';

  return (
    <header className="fixed top-0 left-0 right-0 md:left-64 z-30 bg-background/80 backdrop-blur-xl border-b border-border">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-6 sm:py-0 sm:h-16 sm:gap-4">
        <button
          type="button"
          onClick={onMenuClick}
          className="order-1 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border text-sidebar-foreground hover:bg-accent/50 md:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>
        {/* Search */}
        <form
          onSubmit={handleSearch}
          className="order-3 w-full flex gap-2 sm:order-2 sm:w-auto sm:flex-1"
        >
          <div className="relative flex-1 z-40">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search books, authors, or series..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setShowResults(true)}
              onBlur={() => setTimeout(() => setShowResults(false), 200)}
              className="pl-10 bg-secondary border-border focus:ring-primary"
            />
            {showResults && debouncedQuery.length > 1 && (
              <SearchResults
                results={groupedResults}
                query={debouncedQuery}
                isLoading={isSearching}
                isFetched={isFetched}
              />
            )}
          </div>
          <Button
            type="submit"
            variant="default"
            className="px-4 sm:px-6"
            disabled={!searchQuery.trim()}
          >
            Search
          </Button>
        </form>

        {/* User Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="order-2 ml-auto flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background sm:order-3">
              <Avatar className={`h-9 w-9 border-2 border-primary cursor-pointer ${avatarColor}`}>
                <AvatarFallback className="text-white font-semibold bg-transparent">
                  {user ? getInitials(user.full_name, user.username) : <User className="h-4 w-4" />}
                </AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64 bg-card border-border">
            {/* User Info Header */}
            <div className="flex items-center gap-3 px-3 py-3">
              <Avatar className={`h-12 w-12 ${avatarColor}`}>
                <AvatarFallback className="text-lg font-semibold text-white bg-transparent">
                  {user ? getInitials(user.full_name, user.username) : 'U'}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-foreground truncate">{user?.username || 'User'}</p>
                <p className="text-sm text-muted-foreground truncate">{user?.email || ''}</p>
              </div>
            </div>
            <DropdownMenuSeparator />
            
            {/* Menu Items */}
            <DropdownMenuItem asChild>
              <Link to="/profile" className="flex items-center gap-3 cursor-pointer">
                <User className="h-4 w-4" />
                Profile
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/requests" className="flex items-center gap-3 cursor-pointer">
                <Clock className="h-4 w-4" />
                Requests
              </Link>
            </DropdownMenuItem>
            {isAdmin && (
              <DropdownMenuItem asChild>
                <Link to="/settings" className="flex items-center gap-3 cursor-pointer">
                  <Settings className="h-4 w-4" />
                  Settings
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem 
              onClick={logout}
              className="flex items-center gap-3 cursor-pointer text-destructive focus:text-destructive"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
