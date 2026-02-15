# Tailwind Workflows Reference

## Contents
- Adding New Theme Colors
- Creating Variant Components with CVA
- Adding Custom Animations
- Responsive Design Patterns
- Accessibility Checklist

---

## Adding New Theme Colors

### Workflow Checklist

Copy this checklist and track progress:
- [ ] Step 1: Add CSS custom property in `src/index.css`
- [ ] Step 2: Extend Tailwind config in `tailwind.config.ts`
- [ ] Step 3: Update ThemeContext if theme-switchable
- [ ] Step 4: Test with all 11 theme variants

### Step-by-Step

**1. Add CSS Variable**

```css
/* src/index.css - in :root */
:root {
  /* Existing colors... */
  
  /* Add new semantic color */
  --tertiary: 270 60% 50%;           /* Purple */
  --tertiary-foreground: 270 80% 98%;
}
```

**2. Extend Tailwind Config**

```typescript
// tailwind.config.ts
extend: {
  colors: {
    // Existing colors...
    tertiary: {
      DEFAULT: 'hsl(var(--tertiary))',
      foreground: 'hsl(var(--tertiary-foreground))'
    },
  },
}
```

**3. Use in Components**

```typescript
<div className="bg-tertiary text-tertiary-foreground" />
<div className="border-tertiary/30" />
```

**Validation:**
1. Run `npm run dev`
2. Check browser - color should appear
3. Switch themes in Settings - color should adapt if using CSS variables

---

## Creating Variant Components with CVA

### Pattern from this Codebase

```typescript
// src/components/ui/badge.tsx
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  // Base styles - always applied
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps 
  extends React.HTMLAttributes<HTMLDivElement>, 
  VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
```

### Workflow Checklist

Copy this checklist and track progress:
- [ ] Step 1: Define base styles (always applied)
- [ ] Step 2: Define variant groups (mutually exclusive options)
- [ ] Step 3: Set defaultVariants
- [ ] Step 4: Create TypeScript interface extending VariantProps
- [ ] Step 5: Use cn() to merge variants with className prop
- [ ] Step 6: Export both component and variants function

### Compound Variants

```typescript
const cardVariants = cva("rounded-lg border", {
  variants: {
    intent: { default: "bg-card", elevated: "bg-card-elevated" },
    interactive: { true: "", false: "" },
  },
  compoundVariants: [
    // When BOTH conditions match, apply these classes
    {
      intent: "default",
      interactive: true,
      className: "hover:bg-card/80 cursor-pointer",
    },
  ],
  defaultVariants: { intent: "default", interactive: false },
});
```

---

## Adding Custom Animations

### Workflow Checklist

Copy this checklist and track progress:
- [ ] Step 1: Add keyframes in `tailwind.config.ts`
- [ ] Step 2: Add animation utility in same file
- [ ] Step 3: Test animation in browser
- [ ] Step 4: Add reduced-motion fallback in `src/index.css`

### Adding a New Animation

**1. Define Keyframes**

```typescript
// tailwind.config.ts
keyframes: {
  // Existing keyframes...
  
  'bounce-in': {
    '0%': { transform: 'scale(0.3)', opacity: '0' },
    '50%': { transform: 'scale(1.05)' },
    '70%': { transform: 'scale(0.9)' },
    '100%': { transform: 'scale(1)', opacity: '1' },
  },
},
animation: {
  // Existing animations...
  
  'bounce-in': 'bounce-in 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55)',
},
```

**2. Use in Component**

```typescript
<div className="animate-bounce-in">Content</div>
```

**3. Add Reduced Motion Fallback**

```css
/* src/index.css */
@media (prefers-reduced-motion: reduce) {
  .animate-bounce-in {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
```

---

## Responsive Design Patterns

### Mobile-First Breakpoints

```typescript
// Tailwind default breakpoints
// sm: 640px, md: 768px, lg: 1024px, xl: 1280px, 2xl: 1536px

// Pattern: Start mobile, add complexity at larger screens
<div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4" />

// Hide/show based on screen size
<div className="block md:hidden">Mobile only</div>
<div className="hidden md:block">Desktop only</div>
```

### Container Queries (Custom)

```typescript
// This codebase uses container class with max-width
// tailwind.config.ts
container: {
  center: true,
  padding: '2rem',
  screens: {
    '2xl': '1400px'
  }
}

// Usage
<div className="container mx-auto">
  {/* Max 1400px, centered, 2rem padding */}
</div>
```

### Performance-Aware Responsive

```typescript
// Pattern: Disable expensive effects on mobile
// Already handled by .glass classes in src/index.css

// For custom components:
<div className="backdrop-blur-none md:backdrop-blur-xl" />
<div className="shadow-md md:shadow-xl" />
```

---

## Accessibility Checklist

### Focus States

Every interactive element needs visible focus:

```typescript
// Pattern from this codebase
"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"

// Custom focus utility
<button className="focus-ring">Click me</button>
```

### Color Contrast

| Combination | Minimum Ratio | Check |
|-------------|---------------|-------|
| `text-foreground` on `bg-background` | 4.5:1 | ✅ |
| `text-muted-foreground` on `bg-card` | 4.5:1 | ✅ |
| `text-primary-foreground` on `bg-primary` | 4.5:1 | ✅ |

### Reduced Motion

```css
/* Already in src/index.css */
@media (prefers-reduced-motion: reduce) {
  .animate-pulse-glow,
  .animate-float,
  .shimmer::after {
    animation: none !important;
  }
  
  .card-hover,
  .card-lift {
    transition: none !important;
  }
}
```

### Checklist for New Components

Copy this checklist and track progress:
- [ ] Focus states visible (`focus-visible:ring-2`)
- [ ] Color contrast meets WCAG AA (4.5:1 for text)
- [ ] Reduced motion respected
- [ ] Touch targets >= 44x44px on mobile
- [ ] Semantic HTML elements used (`button`, not `div` with `onClick`)

---

## Debugging Tailwind Issues

### Classes Not Applying

1. Check content paths in `tailwind.config.ts`:
   ```typescript
   content: ["./src/**/*.{ts,tsx}"]
   ```

2. Verify class isn't being overridden - use browser DevTools

3. Check for typos - Tailwind silently ignores invalid classes

### Dynamic Classes Not Working

```typescript
// BAD - Tailwind can't detect these
const color = isActive ? 'primary' : 'secondary';
<div className={`bg-${color}`} />

// GOOD - Full class strings for detection
<div className={isActive ? 'bg-primary' : 'bg-secondary'} />
```

### Conflicts Between Classes

```typescript
// BAD - p-4 and p-2 conflict
<div className="p-4 p-2" /> // Result is unpredictable

// GOOD - Use cn() which uses tailwind-merge
import { cn } from "@/lib/utils";
<div className={cn("p-4", someCondition && "p-2")} /> // p-2 wins when true