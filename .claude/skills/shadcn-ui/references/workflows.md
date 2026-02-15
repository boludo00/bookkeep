# shadcn/ui Workflows Reference

## Contents
- Adding New Components
- Form Handling with react-hook-form
- Loading States Pattern
- Toast Notifications
- Component Customization

---

## Adding New Components

### Workflow: Install shadcn/ui Component

```bash
# Check available components
npx shadcn@latest add --help

# Add a specific component
npx shadcn@latest add alert-dialog

# Add multiple components
npx shadcn@latest add tooltip popover
```

Components install to `src/components/ui/`. The CLI reads `components.json` for configuration.

**Copy this checklist:**
- [ ] Run `npx shadcn@latest add <component>`
- [ ] Verify file created in `src/components/ui/`
- [ ] Import using `@/components/ui/<component>`
- [ ] Test component renders correctly
- [ ] Add theme classes if needed (`bg-card`, `border-border`)

---

## Form Handling with react-hook-form

### Pattern: Form + Zod Validation

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

const schema = z.object({
  url: z.string().url('Must be a valid URL'),
  apiKey: z.string().min(1, 'API key is required'),
});

type FormValues = z.infer<typeof schema>;

function ServerConfigForm() {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { url: '', apiKey: '' },
  });

  const onSubmit = (data: FormValues) => {
    // Handle submission
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="url"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Server URL</FormLabel>
              <FormControl>
                <Input placeholder="https://..." {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Save</Button>
      </form>
    </Form>
  );
}
```

See the **tanstack-query** skill for mutation handling.

---

## Loading States Pattern

### Spinner in Buttons

```tsx
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

<Button disabled={isSubmitting}>
  {isSubmitting ? (
    <>
      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      Submitting...
    </>
  ) : (
    'Submit Request'
  )}
</Button>
```

### Skeleton Loading

```tsx
import { Skeleton } from '@/components/ui/skeleton';

// Loading state
{isLoading ? (
  <div className="space-y-3">
    <Skeleton className="h-4 w-[250px]" />
    <Skeleton className="h-4 w-[200px]" />
  </div>
) : (
  <div>{content}</div>
)}
```

---

## Toast Notifications

Bookkeep uses Sonner (not Radix Toast):

```tsx
import { toast } from 'sonner';

// Success
toast.success('Request submitted!', {
  description: `Your request for "${book.title}" has been submitted.`,
});

// Error
toast.error('Request failed', {
  description: error?.message || 'Please try again.',
});

// Loading state (promise)
toast.promise(asyncOperation(), {
  loading: 'Processing...',
  success: 'Complete!',
  error: 'Failed',
});
```

Toaster is configured in `App.tsx` via `<Toaster />` component.

---

## Component Customization

### Extending Button Variants

To add a new variant, edit `src/components/ui/button.tsx`:

```tsx
const buttonVariants = cva(
  "inline-flex items-center...",
  {
    variants: {
      variant: {
        default: "...",
        // Add new variant
        success: "bg-emerald-600 text-white hover:bg-emerald-700 shadow-md shadow-emerald-600/20",
      },
      // ...
    },
  },
);
```

### Custom Badge Styles via className

Don't modify `badge.tsx`—use `className` for one-off styles:

```tsx
// For status-specific colors
<Badge 
  variant="outline" 
  className="border-destructive/40 text-destructive"
>
  Not Found
</Badge>

<Badge 
  variant="outline" 
  className="border-emerald-500/40 text-emerald-400"
>
  Available
</Badge>
```

---

## Iteration Pattern: Dialog Forms

1. Build form UI with components
2. Add react-hook-form with validation
3. Test validation shows FormMessage errors
4. Wire up mutation (see **tanstack-query** skill)
5. Add loading state to submit button
6. Add toast notifications for success/error
7. Verify dialog closes on successful submission

**Validation loop:**
1. Fill form and submit
2. Check console for errors
3. If validation fails, fix schema or field registration
4. Repeat until form submits successfully