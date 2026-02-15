# Design Patterns Reference

## Contents
- Visual Hierarchy
- Anti-Patterns to Avoid
- Component Consistency
- Accessibility Patterns
- Theme-Safe Patterns

---

## Visual Hierarchy

### Page Structure

```
1. Page Title (text-3xl font-bold)
2. Subtitle/Description (text-muted-foreground)
3. Primary Content Section
   - Section Header (text-2xl font-semibold)
   - Content Cards (glass bg, rounded-xl)
4. Secondary Content
5. Footer Actions
```

### Card Content Order

```tsx
<Card>
  <CardHeader>
    {/* 1. Visual indicator (badge, icon) */}
    {/* 2. Title (font-semibold) */}
    {/* 3. Description (text-muted-foreground) */}
  </CardHeader>
  <CardContent>
    {/* 4. Primary content */}
  </CardContent>
  <CardFooter>
    {/* 5. Actions (buttons, links) */}
  </CardFooter>
</Card>
```

---

## Anti-Patterns to Avoid

### WARNING: Generic AI Aesthetics

**The Problem:**

```tsx
// BAD - Cookie-cutter gradient that looks AI-generated
<div className="bg-gradient-to-r from-purple-500 to-pink-500">
  <h1 className="font-inter">Welcome</h1>
</div>
```

**Why This Breaks:**
1. Purple-pink gradients are overused in AI-generated designs
2. Inter/Roboto are default choices that lack character
3. Doesn't match Bookkeep's cinematic jewel-tone identity

**The Fix:**

```tsx
// GOOD - Uses project's established aesthetic
<div className="relative">
  <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-accent/5" />
  <h1 className="font-sans text-gradient-emerald">Welcome</h1>
</div>
```

---

### WARNING: Hardcoded Colors

**The Problem:**

```tsx
// BAD - Breaks theme switching
<Badge className="bg-green-500 text-white">Available</Badge>
<Button className="bg-[#2dd4bf]">Submit</Button>
```

**Why This Breaks:**
1. Ignores CSS custom properties
2. Won't update when user switches theme
3. Creates visual inconsistency

**The Fix:**

```tsx
// GOOD - Uses design tokens
<Badge className="status-available">Available</Badge>
<Button className="bg-primary text-primary-foreground">Submit</Button>
```

---

### WARNING: Excessive Blur Stacking

**The Problem:**

```tsx
// BAD - Performance nightmare
<div className="backdrop-blur-xl">
  <Card className="backdrop-blur-lg">
    <div className="backdrop-blur-sm">{content}</div>
  </Card>
</div>
```

**Why This Breaks:**
1. Each blur layer is GPU-intensive
2. Stacked blurs compound performance cost
3. Visual result is muddy, not refined

**The Fix:**

```tsx
// GOOD - Single blur at appropriate level
<Card className="glass">
  <div>{content}</div>
</Card>
```

---

### WARNING: Inconsistent Radius

**The Problem:**

```tsx
// BAD - Mixed border radius values
<Card className="rounded-md">
  <Button className="rounded-full">
    <Badge className="rounded-lg">
```

**Why This Breaks:**
1. Creates visual discord
2. Design system has defined radius scale
3. Makes UI feel unpolished

**The Fix:**

```tsx
// GOOD - Consistent radius from design tokens
<Card className="rounded-xl">        {/* Large containers */}
  <Button className="rounded-lg">    {/* Interactive elements */}
    <Badge className="rounded-full"> {/* Pills/badges */}
```

---

## Component Consistency

### Button Hierarchy

```tsx
// Primary action (1 per view)
<Button>Request Book</Button>

// Secondary actions
<Button variant="outline">Cancel</Button>
<Button variant="ghost">More Options</Button>

// Destructive
<Button variant="destructive">Delete</Button>
```

### Input Field Pattern

```tsx
// All inputs follow this pattern
<div className="space-y-2">
  <Label htmlFor="field">Label</Label>
  <Input
    id="field"
    className="h-11 rounded-xl bg-card/50 border-border/50 
               focus:bg-card focus:border-primary/30 
               transition-all duration-300"
  />
  {error && <p className="text-sm text-destructive">{error}</p>}
</div>
```

### Section Divider

```tsx
// Use gradient line, not plain border
<div className="flex items-center gap-4 my-8">
  <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border to-transparent" />
  <span className="text-xs text-muted-foreground uppercase tracking-wider">Section</span>
  <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border to-transparent" />
</div>
```

---

## Accessibility Patterns

### Focus States

```tsx
// All interactive elements need visible focus
<Button className="focus-visible:ring-2 focus-visible:ring-ring 
                   focus-visible:ring-offset-2 focus-visible:ring-offset-background">
```

### Color Contrast

```tsx
// DON'T rely on color alone
<Badge className="status-denied">
  <XCircle className="h-3 w-3 mr-1" /> {/* Icon reinforces meaning */}
  Denied
</Badge>
```

### Touch Targets

```tsx
// Minimum 44x44px for touch
<Button size="icon" className="h-11 w-11">
  <Menu className="h-5 w-5" />
</Button>
```

---

## Theme-Safe Patterns

### Always Use CSS Variables

```tsx
// Colors
className="bg-primary text-primary-foreground"
className="bg-card border-border"
className="text-muted-foreground"

// NOT
className="bg-emerald-500 text-white"
className="bg-slate-800 border-slate-700"
```

### Opacity Modifiers Are Safe

```tsx
// These work with any theme
className="bg-primary/10"
className="border-border/50"
className="text-foreground/80"
```

### Test with Multiple Themes

Copy this checklist when building new components:
- [ ] Test with Emerald Night (default)
- [ ] Test with Sapphire theme
- [ ] Test with Monochrome theme
- [ ] Verify text remains readable
- [ ] Verify focus states are visible

See the **tailwind** skill for complete color token reference.