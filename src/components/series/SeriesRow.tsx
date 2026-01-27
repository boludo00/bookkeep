import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';

interface SeriesRowItem {
  id: number;
  name: string;
  books_count?: number | null;
}

interface SeriesRowProps {
  series: SeriesRowItem[];
  showRequest?: boolean;
  onRequestSeries?: (seriesId: number) => void;
  requestingSeriesId?: number | null;
  requestDisabled?: boolean;
}

export function SeriesRow({
  series,
  showRequest = false,
  onRequestSeries,
  requestingSeriesId = null,
  requestDisabled = false,
}: SeriesRowProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = () => {
    if (!scrollRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
    setCanScrollLeft(scrollLeft > 0);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 1);
  };

  useEffect(() => {
    checkScroll();
    const container = scrollRef.current;
    if (!container) return;
    container.addEventListener('scroll', checkScroll);
    window.addEventListener('resize', checkScroll);
    return () => {
      container.removeEventListener('scroll', checkScroll);
      window.removeEventListener('resize', checkScroll);
    };
  }, [series]);

  const scroll = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const scrollAmount = 420;
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -scrollAmount : scrollAmount,
      behavior: 'smooth',
    });
  };

  return (
    <div className="relative group">
      {canScrollLeft && (
        <Button
          variant="secondary"
          size="icon"
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 h-10 w-10 rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => scroll('left')}
        >
          <ChevronLeft className="h-5 w-5" />
        </Button>
      )}
      <div
        ref={scrollRef}
        className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-4 px-4"
      >
        {series.map((item) => (
          <Link
            key={item.id}
            to={`/series/${item.id}`}
            className="group/series relative flex-shrink-0 w-[220px] rounded-xl border border-border bg-card/70 p-4 transition-[border-color,background-color] hover:border-primary/40 hover:bg-card"
          >
            <div className="space-y-2">
              <h3 className="text-base font-semibold text-foreground line-clamp-2">
                {item.name}
              </h3>
              {item.books_count != null && (
                <p className="text-sm text-muted-foreground">
                  {item.books_count} book{item.books_count === 1 ? '' : 's'}
                </p>
              )}
              {showRequest && onRequestSeries && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2 w-full"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onRequestSeries(item.id);
                  }}
                  disabled={requestDisabled || requestingSeriesId === item.id}
                >
                  {requestingSeriesId === item.id ? 'Requesting…' : 'Request series'}
                </Button>
              )}
            </div>
            <span className="absolute right-4 top-4 text-muted-foreground group-hover/series:text-primary transition-colors">
              →
            </span>
          </Link>
        ))}
      </div>
      {canScrollRight && (
        <Button
          variant="secondary"
          size="icon"
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 h-10 w-10 rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => scroll('right')}
        >
          <ChevronRight className="h-5 w-5" />
        </Button>
      )}
    </div>
  );
}
