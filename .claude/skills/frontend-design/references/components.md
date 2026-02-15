# Components Reference

## Contents
- Button Patterns
- Card Composition
- Form Elements
- Status Indicators
- Book-Specific Components

---

## Button Patterns

### Primary Action

```tsx
<Button className="bg-primary text-primary-foreground shadow-lg shadow-primary/20 
                   hover:bg-primary/90 hover:shadow-primary/30 transition-all duration-300">
  <Plus className="h-4 w-4 mr-2" />
  Request Book
</Button>
```

### Secondary/Ghost

```tsx
<Button variant="ghost" className="hover:bg-card hover:border-primary/30 
                                    transition-all duration-300 rounded-xl">
  <Settings className="h-4 w-4" />
</Button>
```

### Icon Button (Square)

```tsx
<Button size="icon" variant="outline" 
        className="h-10 w-10 rounded-xl border-border/50 hover:border-primary/30">
  <ChevronLeft className="h-5 w-5" />
</Button>
```

---

## Card Composition

### Basic Glass Card

```tsx
<Card className="glass rounded-xl overflow-hidden">
  <CardHeader className="space-y-1">
    <CardTitle className="text-lg font-semibold tracking-tight">
      {title}
    </CardTitle>
    <CardDescription className="text-sm text-muted-foreground">
      {description}
    </CardDescription>
  </CardHeader>
  <CardContent>
    {children}
  </CardContent>
</Card>
```

### Interactive Card with Hover

```tsx
<div className="group card-hover rounded-xl border border-border/50 bg-card/50 
                overflow-hidden cursor-pointer">
  <div className="p-4 space-y-3">
    <h3 className="font-semibold transition-colors group-hover:text-primary">
      {title}
    </h3>
    <p className="text-sm text-muted-foreground">{description}</p>
  </div>
  <div className="px-4 pb-4 flex items-center text-sm text-primary opacity-0 
                  group-hover:opacity-100 transition-opacity duration-300">
    View Details
    <ArrowRight className="h-4 w-4 ml-1 transition-transform group-hover:translate-x-1" />
  </div>
</div>
```

### DO: Layer glass effects properly

```tsx
// GOOD - Subtle base, stronger on focus
<Card className="glass-subtle hover:glass transition-all duration-300">
```

### DON'T: Stack multiple blur effects

```tsx
// BAD - Performance killer, visual muddle
<Card className="backdrop-blur-xl">
  <div className="backdrop-blur-lg">
    <div className="backdrop-blur-md">...</div>
  </div>
</Card>
```

---

## Form Elements

### Search Input

```tsx
<div className="relative">
  <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
  <Input
    className="pl-11 pr-4 h-11 rounded-xl bg-card/50 border-border/50 
               focus:bg-card focus:border-primary/30 transition-all duration-300"
    placeholder="Search books..."
  />
</div>
```

### Select Dropdown

```tsx
<Select>
  <SelectTrigger className="h-11 rounded-xl bg-card/50 border-border/50 
                            focus:border-primary/30 transition-all duration-300">
    <SelectValue placeholder="Select format" />
  </SelectTrigger>
  <SelectContent className="bg-card border-border/50 rounded-xl shadow-2xl">
    <SelectItem value="ebook">eBook</SelectItem>
    <SelectItem value="audiobook">Audiobook</SelectItem>
  </SelectContent>
</Select>
```

---

## Status Indicators

### Badge System

```tsx
// Use predefined status classes
const statusClasses = {
  pending: 'status-requested',
  approved: 'status-approved',
  processing: 'status-processing',
  available: 'status-available',
  denied: 'status-denied',
};

<Badge className={cn(statusClasses[status], 'rounded-full px-2.5 py-1 text-xs font-medium border')}>
  {status}
</Badge>
```

### Format Badges (Book Covers)

```tsx
<div className="absolute top-2 right-2 flex gap-1">
  {hasEbook && (
    <span className="flex items-center gap-1 px-2 py-1 rounded-full 
                     bg-emerald-500/90 text-white text-xs font-medium backdrop-blur-sm">
      <BookOpen className="h-3 w-3" />
      eBook
    </span>
  )}
  {hasAudiobook && (
    <span className="flex items-center gap-1 px-2 py-1 rounded-full 
                     bg-violet-500/90 text-white text-xs font-medium backdrop-blur-sm">
      <Headphones className="h-3 w-3" />
      Audio
    </span>
  )}
</div>
```

---

## Book-Specific Components

### Book Cover with Glow

```tsx
<div className="book-cover-glow">
  <div className="book-cover aspect-[2/3] overflow-hidden rounded-lg">
    <img
      src={coverUrl}
      alt={title}
      className="h-full w-full object-cover transition-transform duration-500 
                 group-hover:scale-105"
      loading="lazy"
    />
    {/* Hover overlay */}
    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent 
                    opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
  </div>
</div>
```

### Rating Display

```tsx
<div className="flex items-center gap-1.5 text-sm">
  <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
  <span className="font-medium">{rating.toFixed(1)}</span>
  <span className="text-muted-foreground">({ratingCount})</span>
</div>
```

See the **shadcn-ui** skill for base component primitives.