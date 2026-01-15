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
