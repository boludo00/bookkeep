# Aesthetics Reference

## Contents
- Color System
- Typography
- Visual Identity
- Shadows and Depth
- Theme Variants

---

## Color System

Bookkeep uses HSL-based CSS custom properties for dynamic theming.

### Primary Palette

```css
/* Core - Deep Navy Base */
--background: 220 20% 4%;      /* #0a0b0d */
--foreground: 45 20% 95%;      /* Off-white, warm */

/* Primary - Emerald (Jewel Tone) */
--primary: 158 64% 42%;        /* Vibrant emerald */
--primary-foreground: 158 50% 98%;

/* Accent - Warm Amber */
--accent: 38 92% 55%;          /* Golden amber */
--accent-foreground: 38 100% 10%;
```

### Semantic Colors

```tsx
// Status badges - use these classes from index.css
<span className="status-requested">Pending</span>   // amber-500
<span className="status-approved">Approved</span>   // sky-500
<span className="status-processing">Processing</span> // violet-500
<span className="status-available">Available</span>  // emerald-500
<span className="status-denied">Denied</span>       // rose-500
```

### DO: Use semantic color tokens

```tsx
// GOOD - Uses design tokens
<Button className="bg-primary hover:bg-primary/90">Submit</Button>
<Badge className="bg-destructive text-destructive-foreground">Error</Badge>
```

### DON'T: Hardcode color values

```tsx
// BAD - Hardcoded colors break theming
<Button className="bg-[#2dd4bf] hover:bg-[#14b8a6]">Submit</Button>
<Badge className="bg-red-500 text-white">Error</Badge>
```

---

## Typography

### Font Stack

```css
/* Sans - UI Text (Outfit) */
font-family: 'Outfit', ui-sans-serif, system-ui, sans-serif;

/* Serif - Editorial (Crimson Pro) */
font-family: 'Crimson Pro', ui-serif, Georgia, serif;

/* Mono - Technical (JetBrains Mono) */
font-family: 'JetBrains Mono', ui-monospace, monospace;
```

### Hierarchy

```tsx
// Page title
<h1 className="text-3xl font-bold tracking-tight">Discover</h1>

// Section heading
<h2 className="text-2xl font-semibold tracking-tight">Trending Books</h2>

// Card title
<h3 className="text-lg font-semibold">Book Title</h3>

// Body text
<p className="text-sm text-muted-foreground">Description...</p>

// Small metadata
<span className="text-xs text-muted-foreground">Published 2024</span>
```

### DO: Use tracking-tight for headings

```tsx
// GOOD - Tighter letter-spacing for large text
<h1 className="text-3xl font-bold tracking-tight">Page Title</h1>
```

### DON'T: Mix font families arbitrarily

```tsx
// BAD - Inconsistent typography
<h1 className="font-serif">Title</h1>
<p className="font-mono">Body text in monospace</p>
```

---

## Visual Identity

### Cinematic Lighting

Ambient glow effects create depth without overwhelming content.

```tsx
// Page-level ambient glow
<div className="absolute -top-40 -left-40 w-96 h-96 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
<div className="absolute -bottom-40 -right-40 w-96 h-96 bg-accent/5 rounded-full blur-3xl pointer-events-none" />
```

### Gradient Text

```tsx
// Emerald gradient for primary headings
<h2 className="text-gradient-emerald text-2xl font-bold">Featured</h2>

// Amber gradient for accents
<span className="text-gradient-amber font-semibold">New Release</span>

// Jewel gradient for special emphasis
<h1 className="text-gradient-jewel text-4xl font-bold">Welcome</h1>
```

---

## Shadows and Depth

### Shadow Scale

```css
--shadow-2xs: 0 1px 2px 0 hsl(0 0% 0% / 0.2);
--shadow-xs:  0 1px 3px 0 hsl(0 0% 0% / 0.25);
--shadow-sm:  0 2px 6px 0 hsl(0 0% 0% / 0.3);
--shadow:     0 4px 12px 0 hsl(0 0% 0% / 0.35);
--shadow-md:  0 6px 16px 0 hsl(0 0% 0% / 0.4);
--shadow-lg:  0 10px 30px 0 hsl(0 0% 0% / 0.5);
--shadow-xl:  0 20px 50px 0 hsl(0 0% 0% / 0.6);
--shadow-2xl: 0 30px 60px 0 hsl(0 0% 0% / 0.7);
```

### Glow Effects

```tsx
// Primary glow for buttons/CTAs
<Button className="shadow-lg shadow-primary/20 hover:shadow-primary/30">
  Action
</Button>

// CSS custom glow for book covers
<div className="book-cover-glow">
  <img className="book-cover" src={cover} alt={title} />
</div>
```

---

## Theme Variants

11 built-in themes available via ThemeContext:

| Theme | Primary | Accent |
|-------|---------|--------|
| Emerald Night | `158 64% 42%` | `38 92% 55%` |
| Sapphire | `217 91% 55%` | `38 92% 55%` |
| Amethyst | `270 60% 55%` | `340 75% 55%` |
| Rose Gold | `340 75% 55%` | `38 92% 55%` |
| Ocean Depths | `195 85% 45%` | `175 70% 40%` |

Always use CSS variables (`bg-primary`, `text-accent`) to support theme switching.