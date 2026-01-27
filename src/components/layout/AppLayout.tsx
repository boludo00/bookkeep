import { Outlet } from 'react-router-dom';
import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Sheet, SheetContent } from '@/components/ui/sheet';

export function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background relative">
      {/* Cinematic ambient background effects – hidden on mobile to save GPU */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden hidden md:block">
        {/* Top-left emerald glow */}
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-primary/5 rounded-full blur-[120px]" />
        {/* Bottom-right amber glow */}
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-amber-500/5 rounded-full blur-[120px]" />
        {/* Center subtle radial */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-gradient-radial from-primary/3 to-transparent rounded-full" />
      </div>

      {/* Sidebar */}
      <Sidebar className="hidden md:flex" />

      {/* Mobile navigation sheet */}
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="p-0 w-72 border-border/50">
          <Sidebar variant="mobile" />
        </SheetContent>
      </Sheet>

      {/* Header */}
      <Header onMenuClick={() => setMobileNavOpen(true)} />

      {/* Main content */}
      <main className="relative pt-24 sm:pt-16 md:ml-64">
        <div className="p-4 sm:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
