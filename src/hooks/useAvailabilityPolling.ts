import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { readarrApi } from '@/lib/api';
import { usePageVisibility } from '@/hooks/usePageVisibility';

interface PendingRequest {
  hardcoverId: number;
  format: 'ebook' | 'audiobook';
  readarrBookId: number | null;
}

interface AvailabilityPollingOptions {
  /** Array of hardcover IDs that have pending requests */
  pendingRequests: PendingRequest[];
  /** Enabled state for the polling */
  enabled?: boolean;
  /** Series ID for query invalidation (optional) */
  seriesId?: string | number;
}

/**
 * Hook to poll Readarr for availability updates on books with pending requests.
 * Uses exponential backoff to reduce API calls:
 * - First 5 minutes: poll every 30 seconds
 * - 5-15 minutes: poll every 2 minutes
 * - After 15 minutes: poll every 5 minutes
 *
 * Automatically invalidates queries when books become available.
 */
export function useAvailabilityPolling({
  pendingRequests,
  enabled = true,
  seriesId,
}: AvailabilityPollingOptions) {
  const queryClient = useQueryClient();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(Date.now());
  const previousAvailabilityRef = useRef<Map<number, { ebook: boolean; audiobook: boolean }>>(new Map());
  const isVisible = usePageVisibility();

  useEffect(() => {
    // Reset start time when pending requests change
    if (pendingRequests.length > 0) {
      startTimeRef.current = Date.now();
    }
  }, [pendingRequests.length]);

  useEffect(() => {
    if (!enabled || pendingRequests.length === 0 || !isVisible) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      return;
    }

    let cancelled = false;

    const checkAvailability = async () => {
      try {
        // Get unique hardcover IDs with readarr book IDs
        const hardcoverIds = [...new Set(pendingRequests.map(r => r.hardcoverId))];

        // Check availability for all pending books
        const result = await readarrApi.getAvailabilityBatch(hardcoverIds);

        // Track which books have become available
        const newlyAvailable: number[] = [];

        result.results.forEach((item) => {
          const previous = previousAvailabilityRef.current.get(item.hardcover_id);
          const current = { ebook: item.ebook, audiobook: item.audiobook };

          // Check if any format became newly available
          if (previous) {
            const ebookBecameAvailable = !previous.ebook && current.ebook;
            const audiobookBecameAvailable = !previous.audiobook && current.audiobook;

            if (ebookBecameAvailable || audiobookBecameAvailable) {
              newlyAvailable.push(item.hardcover_id);
            }
          }

          // Update tracking
          previousAvailabilityRef.current.set(item.hardcover_id, current);
        });

        // If any books became available, invalidate relevant queries
        if (newlyAvailable.length > 0) {
          // Invalidate availability queries
          queryClient.invalidateQueries({ queryKey: ['readarr', 'availability'] });

          // Invalidate request status queries
          queryClient.invalidateQueries({ queryKey: ['requests'] });
          queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover'] });
          queryClient.invalidateQueries({ queryKey: ['book-requests'] });

          // Invalidate series queries if seriesId is provided
          if (seriesId) {
            queryClient.invalidateQueries({ queryKey: ['series', seriesId] });
            queryClient.invalidateQueries({ queryKey: ['requests', 'by-hardcover', 'series', seriesId] });
            queryClient.invalidateQueries({ queryKey: ['readarr', 'availability', 'series', seriesId] });
          }

          // Invalidate series list queries
          queryClient.invalidateQueries({ queryKey: ['popular-series'] });
          queryClient.invalidateQueries({ queryKey: ['readarr', 'availability', 'series-list'] });

          console.log(`[Availability Polling] ${newlyAvailable.length} book(s) became available:`, newlyAvailable);
        }
      } catch (error) {
        console.error('[Availability Polling] Error checking availability:', error);
      }
    };

    // Determine polling interval based on elapsed time
    const getPollingInterval = () => {
      const elapsedMinutes = (Date.now() - startTimeRef.current) / 1000 / 60;

      if (elapsedMinutes < 5) {
        return 60 * 1000; // 60 seconds for first 5 minutes
      } else if (elapsedMinutes < 15) {
        return 3 * 60 * 1000; // 3 minutes for 5-15 minutes
      } else {
        return 5 * 60 * 1000; // 5 minutes after 15 minutes
      }
    };

    // Initial check
    checkAvailability();

    // Use chained setTimeout instead of setInterval to avoid stacking
    const scheduleNextCheck = () => {
      if (cancelled) return;
      const interval = getPollingInterval();
      timeoutRef.current = setTimeout(async () => {
        await checkAvailability();
        scheduleNextCheck();
      }, interval);
    };

    scheduleNextCheck();

    // Cleanup
    return () => {
      cancelled = true;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [enabled, pendingRequests, queryClient, seriesId, isVisible]);

  return null;
}
