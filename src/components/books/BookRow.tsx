import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useRef, useState, useEffect } from 'react';
import { BookCard } from './BookCard';
import { Button } from '@/components/ui/button';
import type { Book } from '@/types/book';

interface BookRowProps {
  title?: string;
  books: Book[];
  viewAllLink?: string;
  requestStatusMap?: Map<number, { ebook: string | null; audiobook: string | null }>;
}

export function BookRow({ title, books, viewAllLink, requestStatusMap }: BookRowProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = () => {
    if (scrollRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
      setCanScrollLeft(scrollLeft > 0);
      setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 1);
    }
  };

  useEffect(() => {
    checkScroll();
    const container = scrollRef.current;
    if (container) {
      container.addEventListener('scroll', checkScroll);
      window.addEventListener('resize', checkScroll);
      return () => {
        container.removeEventListener('scroll', checkScroll);
        window.removeEventListener('resize', checkScroll);
      };
    }
  }, [books]);

  const scroll = (direction: 'left' | 'right') => {
    if (scrollRef.current) {
      const scrollAmount = 400;
      scrollRef.current.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth',
      });
    }
  };

  return (
    <section className="mb-12">
      {title && (
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold text-foreground tracking-tight">
              {title}
            </h2>
            <div className="h-px w-16 bg-gradient-to-r from-primary/50 to-transparent hidden sm:block" />
          </div>
          {viewAllLink && (
            <Link
              to={viewAllLink}
              className="group flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-colors duration-300"
            >
              <span>View All</span>
              <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
          )}
        </div>
      )}

      <div className="relative group/row">
        {/* Left scroll button */}
        {canScrollLeft && (
          <Button
            variant="secondary"
            size="icon"
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-2 z-10 h-12 w-12 rounded-xl shadow-xl bg-card border border-border/50 opacity-0 group-hover/row:opacity-100 transition-[opacity,transform,border-color,background-color] duration-300 hover:bg-card hover:border-primary/30 hover:scale-105"
            onClick={() => scroll('left')}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
        )}

        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-4 w-12 bg-gradient-to-r from-background to-transparent z-[5] pointer-events-none opacity-0 group-hover/row:opacity-100 transition-opacity duration-300" />
        <div className="absolute right-0 top-0 bottom-4 w-12 bg-gradient-to-l from-background to-transparent z-[5] pointer-events-none opacity-0 group-hover/row:opacity-100 transition-opacity duration-300" />

        {/* Scrollable book container */}
        <div
          ref={scrollRef}
          className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-4 px-4 scroll-smooth"
        >
          {books.map((book, index) => (
            <div
              key={book.id}
              className="flex-shrink-0 w-[140px] sm:w-[160px] animate-fade-in-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <BookCard
                book={book}
                requestStatus={
                  requestStatusMap
                    ? requestStatusMap.get((book.hardcoverId ?? Number(book.id)) as number)
                    : undefined
                }
              />
            </div>
          ))}
        </div>

        {/* Right scroll button */}
        {canScrollRight && (
          <Button
            variant="secondary"
            size="icon"
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-2 z-10 h-12 w-12 rounded-xl shadow-xl bg-card border border-border/50 opacity-0 group-hover/row:opacity-100 transition-[opacity,transform,border-color,background-color] duration-300 hover:bg-card hover:border-primary/30 hover:scale-105"
            onClick={() => scroll('right')}
          >
            <ChevronRight className="h-5 w-5" />
          </Button>
        )}
      </div>
    </section>
  );
}
