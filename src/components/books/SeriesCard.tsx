import { Link } from 'react-router-dom';
import { BookOpen, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface SeriesCardProps {
  seriesId: number;
  seriesName: string;
  coverUrl?: string;
  bookCount?: number;
}

export function SeriesCard({ seriesId, seriesName, coverUrl, bookCount }: SeriesCardProps) {
  return (
    <div className="relative rounded-xl overflow-hidden bg-card border border-border">
      <div className="flex items-center gap-4 p-4">
        {/* Series Cover/Thumbnail */}
        <div className="flex-shrink-0 w-16 h-24 rounded-lg overflow-hidden bg-secondary">
          {coverUrl ? (
            <img
              src={coverUrl}
              alt={seriesName}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <BookOpen className="h-8 w-8 text-muted-foreground" />
            </div>
          )}
        </div>

        {/* Series Info */}
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-foreground truncate">{seriesName}</h3>
          {bookCount && bookCount > 0 && (
            <p className="text-sm text-muted-foreground">
              {bookCount} {bookCount === 1 ? 'Book' : 'Books'}
            </p>
          )}
        </div>

        {/* View Button */}
        <Link to={`/series/${seriesId}`}>
          <Button variant="secondary" size="sm" className="flex-shrink-0">
            View
            <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </Link>
      </div>
    </div>
  );
}
