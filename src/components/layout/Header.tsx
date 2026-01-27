import { useEffect, useState } from 'react';
import { Search, User, Settings, Clock, LogOut, Menu, ChevronDown } from 'lucide-react';
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
import { ThemeSwitcher } from '@/components/ThemeSwitcher';
import type { Book } from '@/types/book';

function getInitials(name: string | undefined, username: string): string {
  if (name && name.trim()) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  }
  return username?.slice(0, 2).toUpperCase() || 'U';
}

function getAvatarGradient(username: string): string {
  const gradients = [
    'from-emerald-500 to-teal-600',
    'from-amber-500 to-orange-600',
    'from-violet-500 to-purple-600',
    'from-sky-500 to-blue-600',
    'from-rose-500 to-pink-600',
    'from-cyan-500 to-teal-600',
    'from-fuchsia-500 to-purple-600',
    'from-lime-500 to-green-600',
  ];
  const hash = (username || '').split('').reduce((a, b) => a + b.charCodeAt(0), 0);
  return gradients[hash % gradients.length];
}

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
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

  const avatarGradient = user ? getAvatarGradient(user.username) : 'from-secondary to-muted';

  return (
    <header className="fixed top-0 left-0 right-0 md:left-64 z-30">
      {/* Glassmorphic background */}
      <div className="absolute inset-0 bg-background/70 backdrop-blur-xl border-b border-border/50 pointer-events-none" />

      {/* Ambient glow */}
      <div className="absolute inset-x-0 -top-20 h-40 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

      <div className="relative flex flex-wrap items-center gap-3 px-4 py-3 sm:px-6 sm:py-0 sm:h-16 sm:gap-4">
        {/* Mobile menu button */}
        <button
          type="button"
          onClick={onMenuClick}
          className="order-1 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-card/50 text-foreground hover:bg-card hover:border-primary/30 transition-colors duration-300 md:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Search */}
        <form
          onSubmit={handleSearch}
          className="order-3 w-full flex gap-2 sm:order-2 sm:w-auto sm:flex-1 sm:max-w-xl"
        >
          <div className="relative flex-1 z-40">
            <div className={`
              absolute inset-0 rounded-xl transition-[background-color,box-shadow] duration-300 pointer-events-none
              ${isSearchFocused ? 'bg-primary/5 ring-1 ring-primary/30' : 'bg-transparent'}
            `} />
            <Search className={`
              absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors duration-300
              ${isSearchFocused ? 'text-primary' : 'text-muted-foreground'}
            `} />
            <Input
              type="search"
              placeholder="Search books, authors, or series..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => { setShowResults(true); setIsSearchFocused(true); }}
              onBlur={() => { setTimeout(() => setShowResults(false), 200); setIsSearchFocused(false); }}
              className="pl-11 pr-4 h-11 bg-card/50 border-border/50 rounded-xl placeholder:text-muted-foreground/60 focus:bg-card focus:border-primary/30 transition-[background-color,border-color] duration-300"
            />
            {showResults && debouncedQuery.length > 1 && (
              <div className="absolute top-full left-0 right-0 mt-2">
                <SearchResults
                  results={groupedResults}
                  query={debouncedQuery}
                  isLoading={isSearching}
                  isFetched={isFetched}
                />
              </div>
            )}
          </div>
          <Button
            type="submit"
            className="h-11 px-5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-[background-color,box-shadow] duration-300"
            disabled={!searchQuery.trim()}
          >
            Search
          </Button>
        </form>

        {/* Theme Switcher & User Dropdown */}
        <div className="order-2 ml-auto flex items-center gap-2 sm:order-3">
          <ThemeSwitcher />

          {/* User Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-3 rounded-xl p-1.5 pr-3 hover:bg-card/50 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-2 focus:ring-offset-background transition-colors duration-300">
              <Avatar className={`h-9 w-9 ring-2 ring-border bg-gradient-to-br ${avatarGradient}`}>
                <AvatarFallback className="text-white font-semibold text-sm bg-transparent">
                  {user ? getInitials(user.full_name, user.username) : <User className="h-4 w-4" />}
                </AvatarFallback>
              </Avatar>
              <span className="hidden sm:block text-sm font-medium text-foreground">
                {user?.username || 'User'}
              </span>
              <ChevronDown className="hidden sm:block h-4 w-4 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-64 p-2 bg-card border-border/50 rounded-xl shadow-2xl"
          >
            {/* User Info Header */}
            <div className="flex items-center gap-3 px-2 py-3 rounded-lg bg-muted/30">
              <Avatar className={`h-12 w-12 ring-2 ring-border bg-gradient-to-br ${avatarGradient}`}>
                <AvatarFallback className="text-lg font-semibold text-white bg-transparent">
                  {user ? getInitials(user.full_name, user.username) : 'U'}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-foreground truncate">{user?.username || 'User'}</p>
                <p className="text-sm text-muted-foreground truncate">{user?.email || ''}</p>
              </div>
            </div>
            <DropdownMenuSeparator className="my-2 bg-border/50" />

            {/* Menu Items */}
            <DropdownMenuItem asChild className="rounded-lg focus:bg-primary/10 cursor-pointer">
              <Link to="/profile" className="flex items-center gap-3 px-3 py-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/50">
                  <User className="h-4 w-4" />
                </div>
                <span className="font-medium">Profile</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild className="rounded-lg focus:bg-primary/10 cursor-pointer">
              <Link to="/requests" className="flex items-center gap-3 px-3 py-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/50">
                  <Clock className="h-4 w-4" />
                </div>
                <span className="font-medium">Requests</span>
              </Link>
            </DropdownMenuItem>
            {isAdmin && (
              <DropdownMenuItem asChild className="rounded-lg focus:bg-primary/10 cursor-pointer">
                <Link to="/settings" className="flex items-center gap-3 px-3 py-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/50">
                    <Settings className="h-4 w-4" />
                  </div>
                  <span className="font-medium">Settings</span>
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator className="my-2 bg-border/50" />
            <DropdownMenuItem
              onClick={logout}
              className="rounded-lg cursor-pointer text-rose-400 focus:text-rose-400 focus:bg-rose-500/10"
            >
              <div className="flex items-center gap-3 px-3 py-2.5 w-full">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/10">
                  <LogOut className="h-4 w-4" />
                </div>
                <span className="font-medium">Sign Out</span>
              </div>
            </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
