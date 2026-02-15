# Forms Reference

## Contents
- Form State Pattern
- Mutation with Form
- Format Selection
- State Reset on Dialog Close
- Validation

## Form State Pattern

This codebase uses local state for forms with mutations for submission.

From `src/components/books/RequestDialog.tsx`:

```tsx
type FormatSelection = 'ebook' | 'audiobook' | 'both';

export function RequestDialog({ book, open, onOpenChange }: RequestDialogProps) {
  const [selectedFormat, setSelectedFormat] = useState<FormatSelection | null>(null);
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryClient = useQueryClient();

  // Fetch existing state to determine available options
  const { data: existingRequests, isLoading } = useQuery({
    queryKey: ['book-requests', book.hardcoverId],
    queryFn: () => requestsApi.getByHardcoverId(book.hardcoverId),
    enabled: open && !!book.hardcoverId,
  });

  // Derive available formats
  const canRequestEbook = !existingRequests?.ebook;
  const canRequestAudiobook = !existingRequests?.audiobook;

  // Auto-select format based on availability
  useEffect(() => {
    if (!isLoading) {
      if (canRequestEbook && !canRequestAudiobook) setSelectedFormat('ebook');
      else if (canRequestAudiobook && !canRequestEbook) setSelectedFormat('audiobook');
      else if (canRequestEbook) setSelectedFormat('ebook');
    }
  }, [canRequestEbook, canRequestAudiobook, isLoading]);
```

## Mutation with Form

```tsx
const createRequestMutation = useMutation({
  mutationFn: async ({ bookId, format }: { bookId: number; format: string }) => {
    return requestsApi.create({ book_id: bookId, format, notes });
  },
});

const handleSubmit = async () => {
  if (!selectedFormat) return;
  setIsSubmitting(true);

  try {
    const bookId = await ensureBookMutation.mutateAsync();
    
    const formats = selectedFormat === 'both' ? ['ebook', 'audiobook'] : [selectedFormat];
    for (const format of formats) {
      await createRequestMutation.mutateAsync({ bookId, format });
    }

    queryClient.invalidateQueries({ queryKey: ['requests'] });
    queryClient.invalidateQueries({ queryKey: ['book-requests', book.hardcoverId] });

    toast.success('Request submitted!');
    onOpenChange(false);
  } catch (error) {
    toast.error('Request failed', { description: error.message });
  } finally {
    setIsSubmitting(false);
  }
};
```

## State Reset on Dialog Close

```tsx
// Reset form state when dialog closes
useEffect(() => {
  if (!open) {
    setNotes('');
    // Don't reset selectedFormat - let it auto-select on next open
  }
}, [open]);
```

## Form UI Pattern

```tsx
<div className="space-y-6 py-4">
  {/* Format Selection */}
  <div className="space-y-3">
    <Label className="text-foreground">Select Format</Label>
    <div className={cn("grid gap-3", canRequestBoth ? "grid-cols-3" : "grid-cols-2")}>
      <button
        type="button"
        disabled={!canRequestEbook}
        onClick={() => canRequestEbook && setSelectedFormat('ebook')}
        className={cn(
          'flex flex-col items-center gap-2 p-4 rounded-lg border',
          !canRequestEbook && 'opacity-50 cursor-not-allowed',
          selectedFormat === 'ebook'
            ? 'border-primary bg-primary/10'
            : 'border-border bg-secondary/50'
        )}
      >
        <BookOpen className="h-6 w-6" />
        <span>eBook</span>
      </button>
      {/* Similar for audiobook and both */}
    </div>
  </div>

  {/* Notes */}
  <div className="space-y-3">
    <Label htmlFor="notes">Notes (optional)</Label>
    <Textarea
      id="notes"
      value={notes}
      onChange={(e) => setNotes(e.target.value)}
      rows={3}
    />
  </div>
</div>

<div className="flex justify-end gap-3">
  <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
    Cancel
  </Button>
  <Button onClick={handleSubmit} disabled={!selectedFormat || isSubmitting}>
    {isSubmitting ? <><Loader2 className="animate-spin" /> Submitting...</> : 'Submit'}
  </Button>
</div>
```

## react-hook-form Available

The project has `react-hook-form` and `@hookform/resolvers` installed. For complex forms with validation, use:

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  title: z.string().min(1, 'Required'),
  author: z.string().min(1, 'Required'),
});

function BookForm() {
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Input {...register('title')} />
      {errors.title && <span>{errors.title.message}</span>}
    </form>
  );
}
```

See the **shadcn-ui** skill for Form component integration.