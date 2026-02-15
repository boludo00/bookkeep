# Tailwind Patterns Reference

## Contents
- Color System Patterns
- Component Styling Patterns
- Animation Patterns
- Anti-Patterns

---

## Color System Patterns

### HSL Custom Properties

Colors use HSL values without the `hsl()` wrapper for opacity modifier support:

```css
/* src/index.css */
:root {
  --primary: 158 64% 42%;        /* Emerald */
  --primary-foreground: 158 50% 98%;
  --background: 220 20% 4%;
  --card: 220 18% 8%;
}
```

```typescript
// Usage in components - Tailwind wraps with hsl()
<div className="bg-primary" />           // hsl(158 64% 42%)
<div className="bg-primary/20" />        // hsl(158 64% 42% / 0.2)
<div className="border-border/50" />     // 50% opacity border
```

### Semantic Color Tokens

| Token | Purpose | Example |
|-------|---------|---------|
| `primary` | Brand color (emerald) | Buttons, links, focus rings |
| `accent` | Highlight (amber) | Ratings, warnings, emphasis |
| `muted` | De-emphasized | Disabled text, backgrounds |
| `destructive` | Danger actions | Delete buttons, errors |
| `success/warning/info` | Status indicators | Alerts, badges |

### WARNING: Raw Color Values

**The Problem:**

```typescript
// BAD - Breaks theme switching
<div className="bg-emerald-500 text-white" />
```

**Why This Breaks:**
1. Hardcoded colors ignore theme CSS variables
2. User's selected theme (11 variants) has no effect
3. Dark mode contrast issues when mixing raw/semantic colors

**The Fix:**

```typescript
// GOOD - Uses semantic tokens
<div className="bg-primary text-primary-foreground" />
```

---

## Component Styling Patterns

### Button with Shadow Glow

```typescript
// From src/components/ui/button.tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium ring-offset-background transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30",
        outline: "border border-border bg-transparent hover:bg-card hover:border-primary/30",
        ghost: "hover:bg-muted hover:text-foreground",
      },
    },
  }
);
```

### Card with Hover Effects

```typescript
// BookCard hover pattern from src/components/books/BookCard.tsx
<div className="group relative">
  <div className="book-cover-glow">
    <div className="book-cover aspect-[2/3] bg-card overflow-hidden">
      <img className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
      
      {/* Gradient overlay - appears on hover */}
      <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      {/* Content slides up on hover */}
      <div className="absolute bottom-0 left-0 right-0 p-4 translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-[transform,opacity] duration-300">
        <h3 className="font-semibold text-foreground">{title}</h3>
      </div>
    </div>
  </div>
</div>
```

### Status Badges

```typescript
// Custom component classes from src/index.css
<span className="status-requested">Requested</span>  // amber
<span className="status-approved">Approved</span>    // sky  
<span className="status-processing">Processing</span> // violet
<span className="status-available">Available</span>  // emerald
<span className="status-denied">Denied</span>        // rose
```

Each status badge uses the pattern: `bg-{color}/15 text-{color} border-{color}/30`

---

## Animation Patterns

### Radix UI Data-State Animations

```typescript
// Dialog animations tied to Radix state
<DialogContent className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95" />
```

### Staggered List Animations

```typescript
// Manual stagger with inline styles
{items.map((item, index) => (
  <div 
    key={item.id}
    className="animate-fade-in-up"
    style={{ animationDelay: `${index * 50}ms` }}
  />
))}

// Or use stagger utilities (50ms increments)
<div className="animate-fade-in-up stagger-1" /> // 50ms delay
<div className="animate-fade-in-up stagger-2" /> // 100ms delay
```

### Available Animations

| Class | Duration | Effect |
|-------|----------|--------|
| `animate-fade-in` | 0.3s | Opacity 0→1 |
| `animate-fade-in-up` | 0.4s | Opacity + translateY(10px→0) |
| `animate-scale-in` | 0.2s | Opacity + scale(0.95→1) |
| `animate-glow` | 2s infinite | Pulsing box-shadow |
| `animate-pulse-subtle` | 2s infinite | Opacity 1→0.7→1 |

---

## Anti-Patterns

### WARNING: transition-all Overuse

**The Problem:**

```typescript
// BAD - Animates everything, performance hit
<div className="transition-all duration-300 hover:bg-card hover:scale-105" />
```

**Why This Breaks:**
1. Animates properties you don't intend (color, padding, etc.)
2. Causes layout thrashing on complex components
3. GPU can't optimize unknown transitions

**The Fix:**

```typescript
// GOOD - Explicit transition properties
<div className="transition-[background-color,transform] duration-300 hover:bg-card hover:scale-105" />

// Or separate for different durations
<div className="transition-colors duration-300 hover:bg-card" />
```

### WARNING: Backdrop-blur on Mobile

**The Problem:**

```typescript
// BAD - Performance killer on mobile
<div className="backdrop-blur-xl bg-card/60 md:backdrop-blur-xl" />
```

**Why This Breaks:**
1. `backdrop-filter` is GPU-intensive
2. Mobile Safari has known performance issues
3. Low-end Android devices will stutter

**The Fix:**

The codebase already handles this in `src/index.css`:

```css
@media (max-width: 768px) {
  .glass, .glass-subtle, .glass-strong {
    backdrop-filter: none !important;
  }
}
```

Use the `.glass` utility classes instead of raw `backdrop-blur`:

```typescript
// GOOD - Uses optimized glass class
<div className="glass" />
```

### WARNING: Missing cn() for Overrides

**The Problem:**

```typescript
// BAD - className prop is ignored
function Card({ className }) {
  return <div className="bg-card rounded-lg p-4" />;
}
```

**Why This Breaks:**
1. Consumer cannot override styles
2. Violates component composition patterns
3. Tailwind classes conflict without merge

**The Fix:**

```typescript
// GOOD - Merge with cn()
import { cn } from "@/lib/utils";

function Card({ className }) {
  return <div className={cn("bg-card rounded-lg p-4", className)} />;
}
```

### WARNING: Inline Styles for Tailwind-Available Properties

**The Problem:**

```typescript
// BAD - Mixing inline styles with Tailwind
<div style={{ marginTop: '16px', opacity: 0.5 }} className="p-4" />
```

**Why This Breaks:**
1. Inconsistent styling approach
2. Can't use Tailwind's responsive/state modifiers
3. Harder to maintain, no design system enforcement

**The Fix:**

```typescript
// GOOD - Pure Tailwind
<div className="mt-4 opacity-50 p-4" />

// Exception: Dynamic values that MUST be computed
<div style={{ animationDelay: `${index * 50}ms` }} className="animate-fade-in" />