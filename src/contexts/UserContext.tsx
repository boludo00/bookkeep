import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usersApi, ApiUser } from '@/lib/api';

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
    return !!localStorage.getItem('userId');
  });

  const { data: user, isLoading, refetch } = useQuery({
    queryKey: ['currentUser'],
    queryFn: async () => {
      // The API layer handles mock data automatically
      return usersApi.getMe();
    },
    enabled: isLoggedIn,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false,
  });

  const logout = () => {
    localStorage.removeItem('userId');
    setIsLoggedIn(false);
    queryClient.clear();
    window.location.href = '/login';
  };

  const refetchUser = () => {
    refetch();
  };

  // Listen for localStorage changes (e.g., login in another tab)
  useEffect(() => {
    const handleStorageChange = () => {
      const hasUserId = !!localStorage.getItem('userId');
      setIsLoggedIn(hasUserId);
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
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
