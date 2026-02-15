# Motion Reference

## Contents
- Animation Keyframes
- Transition Patterns
- Hover Interactions
- Loading States
- Performance Considerations

---

## Animation Keyframes

Defined in `src/index.css`:

```css
/* Page entrance */
@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Element entrance */
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Scale entrance (modals, popovers) */
@keyframes scale-in {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

/* Slide entrances */
@keyframes slide-in-right {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

/* Glow pulse (active indicators) */
@keyframes glow {
  0%, 100% { box-shadow: 0 0 5px hsl(var(--primary) / 0.5); }
  50% { box-shadow: 0 0 15px hsl(var(--primary) / 0.8); }
}
```

### Usage

```tsx
// Page entrance
<div className="animate-[fade-in-up_0.4s_ease-out]">
  {pageContent}
</div>

// Modal entrance
<DialogContent className="animate-[scale-in_0.2s_ease-out]">

// Pulsing indicator
<span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
```

---

## Transition Patterns

### Default Timing

```tsx
// Standard transition (most elements)
className="transition-all duration-300"

// Slower for cover images
className="transition-transform duration-500"

// Quick for micro-interactions
className="transition-colors duration-200"
```

### Common Transitions

```tsx
// Color change on hover
<Button className="transition-colors duration-300 hover:bg-primary/90">

// Transform + opacity
<div className="transition-all duration-300 opacity-0 group-hover:opacity-100 
                translate-y-2 group-hover:translate-y-0">

// Scale on hover
<img className="transition-transform duration-500 group-hover:scale-105" />

// Shadow intensity
<Card className="transition-shadow duration-300 hover:shadow-lg">
```

---

## Hover Interactions

### Card Hover

```tsx
// Lift effect (translateY + shadow)
<div className="card-lift">
  {/* Moves up 4px + shadow-xl on hover */}
</div>

// Scale effect
<div className="card-hover">
  {/* Scales 1.02x + shadow-lg on hover */}
</div>
```

### Button Hover

```tsx
<Button className="transition-all duration-300 
                   shadow-lg shadow-primary/20 
                   hover:shadow-primary/30 
                   hover:bg-primary/90">
  Action
</Button>
```

### Link with Arrow

```tsx
<Link className="group flex items-center gap-1 text-primary">
  View All
  <ArrowRight className="h-4 w-4 transition-transform duration-300 
                         group-hover:translate-x-1" />
</Link>
```

### Book Cover Hover

```tsx
<div className="group relative">
  {/* Cover image scales */}
  <img className="transition-transform duration-500 group-hover:scale-105" />
  
  {/* Overlay fades in */}
  <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent 
                  opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
  
  {/* Info slides up */}
  <div className="absolute bottom-0 left-0 right-0 p-4 
                  translate-y-4 group-hover:translate-y-0 
                  opacity-0 group-hover:opacity-100 
                  transition-all duration-300">
    <h3>{title}</h3>
  </div>
</div>
```

---

## Loading States

### Shimmer Effect

```tsx
<div className="shimmer h-48 rounded-lg" />

// CSS (in index.css)
.shimmer {
  background: linear-gradient(90deg, 
    hsl(var(--muted)) 0%, 
    hsl(var(--muted-foreground) / 0.1) 50%, 
    hsl(var(--muted)) 100%);
  background-size: 200% 100%;
  animation: shimmer 2s infinite;
}
```

### Skeleton Components

```tsx
// Book card skeleton
<div className="space-y-3">
  <Skeleton className="aspect-[2/3] rounded-lg" />
  <Skeleton className="h-4 w-3/4" />
  <Skeleton className="h-3 w-1/2" />
</div>
```

### Staggered Loading

```tsx
{items.map((item, i) => (
  <div 
    key={item.id} 
    className={cn('animate-[fade-in-up_0.4s_ease-out]', `stagger-${Math.min(i + 1, 6)}`)}
  >
    <Card>{item.content}</Card>
  </div>
))}

// CSS delays: stagger-1 = 50ms, stagger-2 = 100ms, ... stagger-6 = 300ms
```

---

## Performance Considerations

### DO: Disable effects on mobile

```tsx
// Glass effects removed on mobile (≤768px)
<div className="md:backdrop-blur-xl md:bg-card/60">

// Glow effects hidden on mobile
<div className="hidden md:block absolute inset-0 book-cover-glow" />
```

### DO: Respect reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### DON'T: Animate expensive properties

```tsx
// BAD - Triggers layout recalculation
className="transition-all hover:width-full hover:padding-8"

// GOOD - Only animates transform/opacity (GPU-accelerated)
className="transition-transform hover:scale-105"
className="transition-opacity hover:opacity-80"
```

### DON'T: Stack blur effects

```tsx
// BAD - Multiple blur layers kill performance
<div className="backdrop-blur-xl">
  <div className="backdrop-blur-lg">
    <div className="backdrop-blur-md">...</div>
  </div>
</div>

// GOOD - Single blur at container level
<div className="glass">
  <div>{content}</div>
</div>
```

See the **react** skill for performance optimization patterns.