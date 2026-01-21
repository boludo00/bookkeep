export interface Book {
  id: string;
  title: string;
  author: string;
  cover: string;
  description: string;
  publishedDate: string;
  genres: string[];
  rating: number;
  series?: string;
  seriesPosition?: number;
  seriesId?: number;
  isbn?: string;
  pageCount?: number;
  hardcoverId?: number;
  hardcoverSlug?: string;
  defaultEditionId?: number;
  usersCount?: number;
  activitiesCount?: number;
  ebookAvailable?: boolean;
  audiobookAvailable?: boolean;
}

export interface BookRequest {
  id: string;
  bookId: string;
  book: Book;
  userId: string;
  userName: string;
  format: 'ebook' | 'audiobook';
  status: 'requested' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found';
  source?: 'user_request' | 'booklore_import';
  notes?: string;
  adminNotes?: string;
  readarrReceived?: boolean;
  readarrSearchTriggered?: boolean;
  readarrSearchStatusCode?: number;
  readarrMessage?: string;
  createdAt: string;
  updatedAt: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  role: 'user' | 'admin';
}

export interface RequestStatus {
  hardcover_id: number;
  book_id: number | null;
  ebook: 'requested' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found' | null;
  audiobook: 'requested' | 'approved' | 'denied' | 'processing' | 'available' | 'not_found' | null;
  ebook_readarr_book_id?: number | null;
  audiobook_readarr_book_id?: number | null;
}

export interface RequestStatusBatchResponse {
  results: RequestStatus[];
}

export interface AvailabilityStatus {
  hardcover_id: number;
  ebook: boolean;
  audiobook: boolean;
}

export interface AvailabilityBatchResponse {
  results: AvailabilityStatus[];
}

export interface SeriesItem {
  id: number;
  name: string;
  books_count: number;
  owned_count?: number;
  first_book?: {
    id: number;
    title: string;
    image_url?: string;
    contributions?: Array<{
      author?: {
        name: string;
      };
    }>;
  };
}
