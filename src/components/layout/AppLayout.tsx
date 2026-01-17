import { Outlet } from 'react-router-dom';
import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Sheet, SheetContent } from '@/components/ui/sheet';

export function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar className="hidden md:flex" />
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="p-0">
          <Sidebar variant="mobile" />
        </SheetContent>
      </Sheet>
      <Header onMenuClick={() => setMobileNavOpen(true)} />
      <main className="pt-24 sm:pt-16 md:ml-64">
        <div className="p-4 sm:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
