import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usersApi, authApi, isAuthenticated, clearTokens, ApiUser } from '@/lib/api';

interface UserContextType {
  user: ApiUser | null;
  isLoading: boolean;
  isAdmin: boolean;
  isLoggedIn: boolean;
  refetchUser: () => void;
  logout: () => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [isLoggedIn, setIsLoggedIn] = useState(() => {
    return isAuthenticated();
  });

  const { data: oidcConfig } = useQuery({
    queryKey: ['oidc-config-logout'],
    queryFn: () => authApi.getOidcConfig(),
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const { data: user, isLoading, refetch } = useQuery({
    queryKey: ['currentUser'],
    queryFn: async () => {
      return usersApi.getMe();
    },
    enabled: isLoggedIn,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const logout = () => {
    authApi.logout();
    setIsLoggedIn(false);
    queryClient.clear();

    if (oidcConfig?.logout_url) {
      window.location.href = oidcConfig.logout_url;
    } else {
      window.location.href = '/login';
    }
  };

  const refetchUser = () => {
    refetch();
  };

  // Listen for storage changes (e.g., login in another tab)
  useEffect(() => {
    const handleStorageChange = () => {
      const authenticated = isAuthenticated();
      setIsLoggedIn(authenticated);
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Update isLoggedIn when authentication state changes
  useEffect(() => {
    setIsLoggedIn(isAuthenticated());
  }, []);

  const value: UserContextType = {
    user: user || null,
    isLoading,
    isAdmin: user?.is_admin || false,
    isLoggedIn,
    refetchUser,
    logout,
  };

  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
}
