# shadcn/ui Patterns Reference

## Contents
- Component Composition
- Dialog + Form Pattern
- Tabs + Content Pattern
- Status Badge Pattern
- Controlled Components
- Accessibility Patterns
- Anti-Patterns

---

## Component Composition

### Dialog + Form Pattern (RequestDialog)

The standard pattern for modal forms in Bookkeep:

```tsx
// src/components/books/RequestDialog.tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface RequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RequestDialog({ open, onOpenChange }: RequestDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-foreground">Request Book</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Select format and add notes
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6 py-4">
          <div className="space-y-3">
            <Label htmlFor="notes" className="text-foreground">Notes</Label>
            <Textarea
              id="notes"
              placeholder="Any special requests..."
              className="bg-secondary border-border resize-none"
              rows={3}
            />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit}>Submit</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

**Key patterns:**
- Dialog state controlled via `open` and `onOpenChange` props
- `DialogContent` includes explicit theme classes (`bg-card`, `border-border`)
- Footer buttons use `gap-3` for consistent spacing
- Cancel uses `variant="outline"`, primary action uses default

---

## Tabs + Content Pattern

Used for filtering views (Settings, Downloads, Requests):

```tsx
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

<Tabs defaultValue="ebook" className="w-full">
  <TabsList className="grid w-full grid-cols-2">
    <TabsTrigger value="ebook">eBooks</TabsTrigger>
    <TabsTrigger value="audiobook">Audiobooks</TabsTrigger>
  </TabsList>
  <TabsContent value="ebook">
    {/* eBook content */}
  </TabsContent>
  <TabsContent value="audiobook">
    {/* Audiobook content */}
  </TabsContent>
</Tabs>
```

**DO:** Use `defaultValue` for uncontrolled tabs, `value` + `onValueChange` for controlled.

---

## Status Badge Pattern

Consistent status indicators across the app:

```tsx
import { Badge } from '@/components/ui/badge';
import { CheckCircle, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

type Status = 'requested' | 'approved' | 'processing' | 'available' | 'not_found';

const statusConfig: Record<Status, { 
  label: string; 
  variant: 'default' | 'secondary' | 'outline';
  icon?: typeof CheckCircle;
  className?: string;
}> = {
  requested: { label: 'Pending', variant: 'secondary', icon: Clock },
  approved: { label: 'Approved', variant: 'default', icon: Clock },
  processing: { label: 'Processing', variant: 'default', icon: Clock },
  available: { label: 'Available', variant: 'outline', icon: CheckCircle },
  not_found: { label: 'Not Found', variant: 'outline', className: 'border-destructive/40 text-destructive' },
};

function StatusBadge({ status }: { status: Status }) {
  const config = statusConfig[status];
  const Icon = config.icon;
  
  return (
    <Badge variant={config.variant} className={cn('text-xs', config.className)}>
      {Icon && <Icon className="h-3 w-3 mr-1" />}
      {config.label}
    </Badge>
  );
}
```

---

## Controlled Components

### WARNING: Forgetting onOpenChange

**The Problem:**

```tsx
// BAD - Dialog won't close
<Dialog open={isOpen}>
  <DialogContent>...</DialogContent>
</Dialog>
```

**Why This Breaks:** Without `onOpenChange`, clicking overlay or X button does nothing.

**The Fix:**

```tsx
// GOOD - Properly controlled
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>...</DialogContent>
</Dialog>
```

---

## Custom Selection Buttons

Pattern for format/option selection (replaces radio groups):

```tsx
import { cn } from '@/lib/utils';
import { BookOpen, Headphones } from 'lucide-react';

const [selected, setSelected] = useState<'ebook' | 'audiobook'>('ebook');

<div className="grid grid-cols-2 gap-3">
  <button
    type="button"
    onClick={() => setSelected('ebook')}
    className={cn(
      'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all',
      selected === 'ebook'
        ? 'border-primary bg-primary/10 text-primary'
        : 'border-border bg-secondary/50 text-muted-foreground hover:border-muted-foreground'
    )}
  >
    <BookOpen className="h-6 w-6" />
    <span className="text-sm font-medium">eBook</span>
  </button>
  {/* Audiobook button similar */}
</div>
```

---

## Accessibility Patterns

### Form Labels

Always connect labels to inputs:

```tsx
// GOOD
<Label htmlFor="notes">Notes</Label>
<Textarea id="notes" />

// BAD - Missing htmlFor/id connection
<Label>Notes</Label>
<Textarea />
```

### Screen Reader Text

Close buttons include sr-only text by default in DialogContent:

```tsx
// Built into DialogContent - no action needed
<DialogPrimitive.Close>
  <X className="h-4 w-4" />
  <span className="sr-only">Close</span>
</DialogPrimitive.Close>
```

### aria-label for Icon Buttons

```tsx
// GOOD
<button aria-label="Open navigation">
  <Menu className="h-5 w-5" />
</button>

// BAD - No accessible name
<button>
  <Menu className="h-5 w-5" />
</button>
```

---

## Anti-Patterns

### WARNING: Inline Class Strings

**The Problem:**

```tsx
// BAD - Duplicated, error-prone
<Button className="bg-primary text-primary-foreground hover:bg-primary/90">
```

**Why This Breaks:** Duplicates CVA variant logic, may conflict with base styles.

**The Fix:**

```tsx
// GOOD - Use variants
<Button variant="default">
```

### WARNING: Missing Theme Classes on DialogContent

**The Problem:**

```tsx
// BAD - May not match theme
<DialogContent>
```

**The Fix:**

```tsx
// GOOD - Explicit theme classes
<DialogContent className="bg-card border-border">