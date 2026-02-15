# Layouts Reference

## Contents
- App Shell Structure
- Page Templates
- Grid Systems
- Responsive Patterns
- Content Containers

---

## App Shell Structure

### Root Layout

```tsx
<div className="min-h-screen bg-background relative">
  {/* Ambient background effects - hidden on mobile */}
  <div className="hidden md:block pointer-events-none absolute inset-0 overflow-hidden">
    <div className="absolute -top-40 -left-40 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
    <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-accent/5 rounded-full blur-3xl" />
  </div>
  
  {/* Sidebar - desktop only */}
  <Sidebar className="hidden md:flex fixed left-0 top-0 z-40 h-screen w-64" />
  
  {/* Header - fixed */}
  <Header className="fixed top-0 left-0 right-0 md:left-64 z-30" />
  
  {/* Main content */}
  <main className="pt-24 sm:pt-16 md:ml-64 relative z-10">
    <div className="p-4 sm:p-6 lg:p-8">
      {children}
    </div>
  </main>
</div>
```

### Responsive Breakpoints

| Breakpoint | Width | Layout Changes |
|------------|-------|----------------|
| Default | <640px | Full-width, mobile nav, no ambient glow |
| `sm` | 640px | Reduced header padding |
| `md` | 768px | Sidebar visible, header offset |
| `lg` | 1024px | Increased content padding |
| `xl` | 1280px | Max-width containers |

---

## Page Templates

### Standard Page

```tsx
export function StandardPage() {
  return (
    <div className="space-y-8 animate-[fade-in-up_0.4s_ease-out]">
      {/* Page header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Page Title</h1>
        <p className="text-muted-foreground">Page description text</p>
      </div>
      
      {/* Content sections */}
      <section className="space-y-4">
        {/* Section content */}
      </section>
    </div>
  );
}
```

### Settings Page (Multi-Section)

```tsx
export function SettingsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Manage application configuration</p>
      </div>
      
      <Tabs defaultValue="general" className="space-y-6">
        <TabsList className="glass-subtle p-1 rounded-xl">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="downloads">Downloads</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
        </TabsList>
        
        <TabsContent value="general" className="space-y-6">
          <Card className="glass">
            <CardHeader>
              <CardTitle>Section Title</CardTitle>
            </CardHeader>
            <CardContent>{/* ... */}</CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

---

## Grid Systems

### Book Card Grid

```tsx
<div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
  {books.map((book) => (
    <BookCard key={book.id} book={book} />
  ))}
</div>
```

### Horizontal Scroll Row

```tsx
<div className="relative group/row">
  {/* Scroll buttons */}
  <Button
    size="icon"
    variant="outline"
    className="absolute left-0 top-1/2 -translate-y-1/2 z-10 h-12 w-12 rounded-xl 
               opacity-0 group-hover/row:opacity-100 transition-opacity duration-300
               bg-card/90 backdrop-blur-sm shadow-xl"
    onClick={scrollLeft}
  >
    <ChevronLeft className="h-5 w-5" />
  </Button>
  
  {/* Scrollable container */}
  <div className="flex gap-4 overflow-x-auto scroll-smooth scrollbar-hide pb-4">
    {items.map((item) => (
      <div key={item.id} className="flex-shrink-0 w-[180px]">
        <BookCard book={item} />
      </div>
    ))}
  </div>
  
  <Button /* Right button - same pattern */ />
</div>
```

### Two-Column Form Layout

```tsx
<div className="grid gap-6 md:grid-cols-2">
  <div className="space-y-2">
    <Label>Field One</Label>
    <Input />
  </div>
  <div className="space-y-2">
    <Label>Field Two</Label>
    <Input />
  </div>
</div>
```

---

## Content Containers

### Max-Width Constraint

```tsx
// For centered content pages (e.g., book details)
<div className="max-w-4xl mx-auto space-y-8">
  {/* Content */}
</div>
```

### Full-Bleed with Padding

```tsx
// For dashboard/grid pages
<div className="p-4 sm:p-6 lg:p-8 space-y-8">
  {/* Content */}
</div>
```

### DO: Use consistent spacing scale

```tsx
// GOOD - Uses Tailwind's spacing scale
<div className="space-y-8">
  <section className="space-y-4">...</section>
  <section className="space-y-4">...</section>
</div>
```

### DON'T: Mix arbitrary spacing values

```tsx
// BAD - Inconsistent spacing
<div className="space-y-[22px]">
  <section className="mb-7">...</section>
  <section className="mt-[15px]">...</section>
</div>
```

---

## Responsive Patterns

### Mobile-First Padding

```tsx
// Progressive padding increase
<div className="p-4 sm:p-6 lg:p-8">
```

### Hide/Show by Breakpoint

```tsx
// Desktop sidebar, mobile sheet
<Sidebar className="hidden md:flex" />
<MobileNav className="md:hidden" />

// Ambient effects - disable on mobile for performance
<div className="hidden md:block">
  {/* Blur effects */}
</div>
```

### Grid Column Adjustment

```tsx
// 2 cols mobile → 6 cols desktop
<div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
```

See the **tailwind** skill for responsive utility patterns.