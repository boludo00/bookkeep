# State Management Reference

## Contents
- State Categories
- User Context Pattern
- Theme Context Pattern
- URL State
- Query Invalidation

## State Categories

| Category | Solution | Example |
|----------|----------|---------|
| Server state | TanStack Query | Book data, requests |
| Auth state | Context + Query | `UserContext.tsx` |
| Theme state | Context + localStorage | `ThemeContext.tsx` |
| UI state | Local `useState` | Dialog open, form inputs |
| URL state | React Router | Search params, filters |

## User Context Pattern

Combines Context for global access with TanStack Query for server sync.

From `src/contexts/UserContext.tsx`:

```tsx
interface UserContextType {
  user: ApiUser | null;
  isLoading: boolean;
  isAdmin: boolean;
  isLoggedIn: boolean;
  refetchUser: () => void;
  logout: () => void;
}

export function UserProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [isLoggedIn, setIsLoggedIn] = useState(() => isAuthenticated());

  const { data: user, isLoading, refetch } = useQuery({
    queryKey: ['currentUser'],
    queryFn: () => usersApi.getMe(),
    enabled: isLoggedIn,           // Don't fetch if not logged in
    staleTime: 5 * 60 * 1000,      // 5 minutes
    retry: false,                   // Don't retry auth failures
  });

  const logout = () => {
    authApi.logout();
    setIsLoggedIn(false);
    queryClient.clear();            // Clear all cached data
    window.location.href = '/login';
  };

  // Sync with other tabs
  useEffect(() => {
    const handleStorageChange = () => setIsLoggedIn(isAuthenticated());
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  return (
    <UserContext.Provider value={{ user, isLoading, isAdmin: user?.is_admin, logout }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (!context) throw new Error('useUser must be used within UserProvider');
  return context;
}
```

## Theme Context Pattern

From `src/contexts/ThemeContext.tsx`:

```tsx
function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.style.setProperty('--primary', theme.colors.primary);
  root.style.setProperty('--accent', theme.colors.accent);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [currentTheme, setCurrentTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme');
    return themes.find(t => t.name === saved) || themes[0];
  });

  useEffect(() => {
    applyTheme(currentTheme);
  }, [currentTheme]);

  const setTheme = (themeName: string) => {
    const theme = themes.find(t => t.name === themeName);
    if (theme) {
      setCurrentTheme(theme);
      localStorage.setItem('theme', themeName);
    }
  };

  return (
    <ThemeContext.Provider value={{ currentTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

## Query Invalidation After Mutations

When data changes, invalidate related queries to trigger refetch:

```tsx
const queryClient = useQueryClient();

const handleSubmit = async () => {
  await createRequestMutation.mutateAsync(data);
  
  // Invalidate all related query keys
  queryClient.invalidateQueries({ queryKey: ['requests'] });
  queryClient.invalidateQueries({ queryKey: ['book-requests', hardcoverId] });
  queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });
};
```

**Pattern for polling hooks** (from `useAvailabilityPolling.ts`):

```tsx
if (newlyAvailable.length > 0) {
  queryClient.invalidateQueries({ queryKey: ['readarr', 'availability'] });
  queryClient.invalidateQueries({ queryKey: ['requests'] });
  queryClient.invalidateQueries({ queryKey: ['book-requests'] });
  if (seriesId) {
    queryClient.invalidateQueries({ queryKey: ['series', seriesId] });
  }
}
```

## WARNING: useState for Server Data

**The Problem:**

```tsx
// BAD - Server data in useState
const [books, setBooks] = useState([]);
useEffect(() => {
  fetchBooks().then(setBooks);
}, []);
```

**Why This Breaks:**
- No caching across components
- Stale data after navigation
- No automatic refetching

**The Fix:**

```tsx
// GOOD - Server data in Query
const { data: books } = useQuery({
  queryKey: ['books'],
  queryFn: fetchBooks,
});
```

## WARNING: Prop Drilling Past 3 Levels

**The Problem:**

```tsx
// BAD - Drilling user through many levels
<App user={user}>
  <Layout user={user}>
    <Page user={user}>
      <Component user={user} />
    </Page>
  </Layout>
</App>
```

**The Fix:** Use Context:

```tsx
// GOOD - Use UserContext
function Component() {
  const { user, isAdmin } = useUser();
  return <div>{user.name}</div>;
}