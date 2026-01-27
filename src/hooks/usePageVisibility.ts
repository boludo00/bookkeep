import { useState, useEffect } from 'react';

/**
 * Hook that tracks whether the page is currently visible to the user.
 * Returns false when the tab is backgrounded, the screen is locked, etc.
 * Use this to pause polling, animations, and other battery-draining activity.
 */
export function usePageVisibility(): boolean {
  const [isVisible, setIsVisible] = useState(!document.hidden);

  useEffect(() => {
    const handler = () => setIsVisible(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  return isVisible;
}
