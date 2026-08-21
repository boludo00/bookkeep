import type { Book } from '@/types/book';

export interface LibraryAvailability {
  ebook: boolean;
  audiobook: boolean;
}

function normalizeText(value?: string | null): string {
  return (value || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function normalizeIsbn(value?: string | null): string {
  return (value || '').replace(/[^0-9Xx]/g, '').toUpperCase();
}

function splitAuthors(value?: string | null): string[] {
  return (value || '')
    .split(/,|&|\band\b/gi)
    .map(normalizeText)
    .filter(Boolean);
}

function authorsOverlap(a?: string | null, b?: string | null): boolean {
  const left = splitAuthors(a);
  const right = splitAuthors(b);

  if (left.length === 0 || right.length === 0) {
    return false;
  }

  return left.some((author) => right.includes(author));
}

function matchesLibraryBook(book: Book, libraryBook: any): boolean {
  const hardcoverMatch =
    !!book.hardcoverId &&
    !!libraryBook.hardcover_id &&
    book.hardcoverId === libraryBook.hardcover_id;

  const bookIsbn = normalizeIsbn(book.isbn);
  const libraryIsbn = normalizeIsbn(libraryBook.isbn);
  const isbnMatch =
    !!bookIsbn &&
    !!libraryIsbn &&
    bookIsbn === libraryIsbn;

  const titleMatch =
    !!book.title &&
    !!libraryBook.title &&
    normalizeText(book.title) === normalizeText(libraryBook.title);

  const titleAuthorMatch =
    titleMatch &&
    authorsOverlap(book.author, libraryBook.author);

  return hardcoverMatch || isbnMatch || titleAuthorMatch;
}

export function getLibraryAvailability(
  book: Book,
  libraryBooks: any[],
): LibraryAvailability {
  const matches = libraryBooks.filter((libraryBook) =>
    matchesLibraryBook(book, libraryBook),
  );

  return {
    ebook: matches.some((item) => Boolean(item.ebook_available)),
    audiobook: matches.some((item) => Boolean(item.audiobook_available)),
  };
}
