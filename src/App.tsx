import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { UserProvider } from "@/contexts/UserContext";
import { AuthWrapper } from "@/components/AuthWrapper";
import Discover from "@/pages/Discover";
import Browse from "@/pages/Browse";
import BookDetails from "@/pages/BookDetails";
import Requests from "@/pages/Requests";
import Downloads from "@/pages/Downloads";
import Admin from "@/pages/Admin";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import Profile from "@/pages/Profile";
import Series from "@/pages/Series";
import SeriesDetail from "@/pages/SeriesDetail";
import SearchResults from "@/pages/SearchResults";
import Author from "@/pages/Author";
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";
import AdminSetup from "@/pages/AdminSetup";
import { AdminCheckWrapper } from "@/components/AdminCheckWrapper";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <UserProvider>
      <TooltipProvider>
        <Toaster position="bottom-right" theme="dark" />
        <BrowserRouter>
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
                  <Route path="/author" element={<Author />} />
                  <Route path="/profile" element={<Profile />} />
                  <Route path="/admin" element={<Admin />} />
                  <Route path="/admin/users" element={<Users />} />
                  <Route path="/settings" element={<Settings />} />
                </Route>
              </Route>
            </Route>
            
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </UserProvider>
  </QueryClientProvider>
);

export default App;
