# Components Reference

## Contents
- File Organization
- Memoization Pattern
- Scroll State Management
- Dialog Components
- Component Props Interface

## File Organization

```
src/components/
├── ui/              # shadcn primitives (button.tsx, dialog.tsx)
├── books/           # BookCard.tsx, BookRow.tsx, RequestDialog.tsx
├── layout/          # AppLayout.tsx, Header.tsx, Sidebar.tsx
├── series/          # SeriesCard.tsx, SeriesRow.tsx
└── settings/        # Settings section components
```

**Naming:**
- PascalCase for component files: `BookCard.tsx`
- Component name matches filename: `export const BookCard = ...`

## Memoization Pattern

When rendering grids of cards, use `memo()` to prevent unnecessary re-renders.

From `src/components/books/BookCard.tsx:20-27`:

```tsx
interface BookCardProps {
  book: Book;
  status?: 'available' | 'pending' | 'none';
  showRating?: boolean;
  enableRequestStatus?: boolean;
  showRequestButton?: boolean;
  requestStatus?: { ebook?: string | null; audiobook?: string | null };
}

export const BookCard = memo(function BookCard({
  book,
  status = 'none',
  showRating = true,
  enableRequestStatus = false,
  showRequestButton = true,
  requestStatus,
}: BookCardProps) {
  // Component implementation
});
```

**When to use `memo()`:**
- Card components in grids/lists
- Components receiving stable props from parent
- Expensive render logic

**When NOT to use `memo()`:**
- Components that always re-render anyway
- Simple components with fast renders
- Components with frequently changing props

## Scroll State Management

From `src/components/books/BookRow.tsx`:

```tsx
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
    scrollRef.current?.scrollBy({
      left: direction === 'left' ? -400 : 400,
      behavior: 'smooth',
    });
  };

  return (
    <div className="relative group/row">
      {canScrollLeft && (
        <Button onClick={() => scroll('left')}>
          <ChevronLeft />
        </Button>
      )}
      <div ref={scrollRef} className="flex gap-4 overflow-x-auto">
        {books.map((book) => (
          <BookCard key={book.id} book={book} />
        ))}
      </div>
      {canScrollRight && (
        <Button onClick={() => scroll('right')}>
          <ChevronRight />
        </Button>
      )}
    </div>
  );
}
```

## Dialog Components

Dialogs follow a controlled pattern with `open` and `onOpenChange` props.

From `src/components/books/RequestDialog.tsx`:

```tsx
interface RequestDialogProps {
  book: Book;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preferredFormat?: 'ebook' | 'audiobook' | 'both';
  disableFormats?: { ebook?: boolean; audiobook?: boolean };
}

export function RequestDialog({ book, open, onOpenChange }: RequestDialogProps) {
  // Reset state when dialog closes
  useEffect(() => {
    if (!open) setNotes('');
  }, [open]);

  // Fetch data only when dialog is open
  const { data: existingRequests } = useQuery({
    queryKey: ['book-requests', book.hardcoverId],
    queryFn: () => requestsApi.getByHardcoverId(book.hardcoverId),
    enabled: open && !!book.hardcoverId,  // Gate on dialog open
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Dialog content */}
      </DialogContent>
    </Dialog>
  );
}
```

**Key patterns:**
- Gate queries with `enabled: open` to avoid fetching when closed
- Reset local state in `useEffect` when dialog closes
- Use shadcn/ui Dialog from `@/components/ui/dialog`

## WARNING: Inline Object Props

**The Problem:**

```tsx
// BAD - Creates new object every render
<BookCard book={book} requestStatus={{ ebook: null, audiobook: null }} />
```

**Why This Breaks:** New reference every render breaks `memo()` optimization.

**The Fix:**

```tsx
// GOOD - Use Map from parent or stable reference
<BookCard book={book} requestStatus={requestStatusMap.get(book.id)} />
```

## WARNING: Index as Key

**The Problem:**

```tsx
// BAD - Index as key in dynamic list
{books.map((book, index) => <BookCard key={index} book={book} />)}
```

**Why This Breaks:** Reordering/filtering causes React to match wrong items.

**The Fix:**

```tsx
// GOOD - Stable unique ID
{books.map((book) => <BookCard key={book.id} book={book} />)}