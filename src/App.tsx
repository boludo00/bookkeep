import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { UserProvider } from "@/contexts/UserContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { AuthWrapper } from "@/components/AuthWrapper";
import { Loader2 } from "lucide-react";
import { AdminCheckWrapper } from "@/components/AdminCheckWrapper";
import { AdminRouteGuard } from "@/components/AdminRouteGuard";

// Keep Login and NotFound as static imports (entry point + tiny fallback)
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";

// Lazy-load all other pages for code splitting
const Discover = lazy(() => import("@/pages/Discover"));
const Browse = lazy(() => import("@/pages/Browse"));
const BookDetails = lazy(() => import("@/pages/BookDetails"));
const Requests = lazy(() => import("@/pages/Requests"));
const Downloads = lazy(() => import("@/pages/Downloads"));
const Admin = lazy(() => import("@/pages/Admin"));
const Users = lazy(() => import("@/pages/Users"));
const Settings = lazy(() => import("@/pages/Settings"));
const Profile = lazy(() => import("@/pages/Profile"));
const Series = lazy(() => import("@/pages/Series"));
const SeriesDetail = lazy(() => import("@/pages/SeriesDetail"));
const SearchResults = lazy(() => import("@/pages/SearchResults"));
const Author = lazy(() => import("@/pages/Author"));
const PromptDetail = lazy(() => import("@/pages/PromptDetail"));
const AdminSetup = lazy(() => import("@/pages/AdminSetup"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <UserProvider>
      <ThemeProvider>
        <TooltipProvider>
          <Toaster position="bottom-right" theme="dark" />
          <BrowserRouter>
            <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/admin-setup" element={<AdminSetup />} />

              {/* Protected routes - require authentication */}
              <Route element={<AuthWrapper />}>
                <Route element={<AdminCheckWrapper />}>
                  <Route element={<AppLayout />}>
                    <Route path="/" element={<Discover />} />
                    <Route path="/browse/:category" element={<Browse />} />
                    <Route path="/book/:id" element={<BookDetails />} />
                    <Route path="/search" element={<SearchResults />} />
                    <Route path="/requests" element={<Requests />} />
                    <Route path="/downloads" element={<Downloads />} />
                    <Route path="/series" element={<Series />} />
                    <Route path="/series/:id" element={<SeriesDetail />} />
                    <Route path="/prompt/:slug" element={<PromptDetail />} />
                    <Route path="/author" element={<Author />} />
                    <Route path="/profile" element={<Profile />} />
                    <Route element={<AdminRouteGuard />}>
                      <Route path="/admin" element={<Admin />} />
                      <Route path="/admin/users" element={<Users />} />
                      <Route path="/settings" element={<Settings />} />
                    </Route>
                  </Route>
                </Route>
              </Route>

              <Route path="*" element={<NotFound />} />
            </Routes>
            </Suspense>
          </BrowserRouter>
        </TooltipProvider>
      </ThemeProvider>
    </UserProvider>
  </QueryClientProvider>
);

export default App;
