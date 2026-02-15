# Build Optimization Reference

## Contents
- Production Build
- Code Splitting
- Bundle Analysis
- Docker Integration
- Common Issues

## Production Build

```bash
npm run build        # Production build
npm run build:dev    # Development build (with sourcemaps)
npm run preview      # Preview production build locally
```

Output structure:

```
dist/
├── index.html
├── assets/
│   ├── index-[hash].js      # Main bundle
│   ├── index-[hash].css     # Extracted CSS
│   ├── Discover-[hash].js   # Lazy-loaded chunk
│   ├── Settings-[hash].js   # Lazy-loaded chunk
│   └── ...
```

## Code Splitting

Bookkeep uses React.lazy() for automatic code splitting:

```typescript
// src/App.tsx
import { Suspense, lazy } from "react";

// Static imports - included in main bundle
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";

// Lazy imports - separate chunks
const Discover = lazy(() => import("@/pages/Discover"));
const Settings = lazy(() => import("@/pages/Settings"));
const BookDetails = lazy(() => import("@/pages/BookDetails"));
```

### When to Lazy Load

| Scenario | Approach |
|----------|----------|
| Entry points (Login) | Static import |
| Large pages (Settings ~51KB) | Lazy load |
| Rarely visited pages | Lazy load |
| Small, frequently used components | Static import |

### WARNING: Missing Suspense Boundary

**The Problem:**

```typescript
// BAD - No Suspense wrapper
const Settings = lazy(() => import("@/pages/Settings"));

<Routes>
  <Route path="/settings" element={<Settings />} />
</Routes>
```

**Why This Breaks:** React throws error: "A component suspended while responding to synchronous input."

**The Fix:**

```typescript
// GOOD - Suspense with fallback
<Suspense fallback={<PageLoader />}>
  <Routes>
    <Route path="/settings" element={<Settings />} />
  </Routes>
</Suspense>
```

## Bundle Analysis

Analyze bundle size:

```bash
# Install analyzer
npm install -D rollup-plugin-visualizer

# Add to vite.config.ts
import { visualizer } from "rollup-plugin-visualizer";

plugins: [
  react(),
  visualizer({ open: true })  // Opens stats.html after build
]
```

## Docker Integration

Multi-stage build for production:

```dockerfile
# Stage 1: Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY vite.config.ts tsconfig*.json ./
COPY tailwind.config.ts postcss.config.js ./
COPY index.html ./
COPY src ./src
COPY public ./public

ENV NODE_ENV=production
RUN npm run build

# Stage 2: Backend serves built frontend
FROM python:3.11-slim
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist
```

### Build Layer Caching

Order Dockerfile commands for optimal caching:

1. Copy package.json first (changes rarely)
2. Install dependencies (cached if package.json unchanged)
3. Copy config files
4. Copy source files last (changes frequently)

## Common Issues

### Build Fails with TypeScript Errors

```bash
# Build ignores TypeScript errors by default
# If strict mode is enabled, fix errors or:
npm run build -- --force
```

### Large Bundle Size

1. Check for accidental full library imports:
   ```typescript
   // BAD - imports entire library
   import _ from "lodash";
   
   // GOOD - tree-shakeable
   import debounce from "lodash/debounce";
   ```

2. Analyze with visualizer plugin
3. Add more lazy loading boundaries

### Assets Not Found in Production

Ensure `build.outDir` matches FastAPI's static file path:

```typescript
// vite.config.ts
build: {
  outDir: "dist",
}
```

```python
# main.py
app.mount("/", StaticFiles(directory="frontend_dist", html=True))
```

## Related Skills

- See the **react** skill for lazy loading patterns
- See the **tailwind** skill for CSS optimization