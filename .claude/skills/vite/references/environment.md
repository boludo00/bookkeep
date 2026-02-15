# Environment Variables Reference

## Contents
- Environment Variable Rules
- Accessing Variables
- Build-time vs Runtime
- Docker Build Args
- Common Patterns

## Environment Variable Rules

Vite only exposes variables prefixed with `VITE_` to client code:

```typescript
// EXPOSED to client (in bundle)
import.meta.env.VITE_API_URL       // Works
import.meta.env.VITE_APP_VERSION   // Works

// NOT EXPOSED (undefined in client)
import.meta.env.DATABASE_URL       // undefined
import.meta.env.SECRET_KEY         // undefined
```

### WARNING: Exposing Secrets

**The Problem:**

```typescript
// .env
VITE_DATABASE_URL=postgresql://user:password@host/db
VITE_API_SECRET=sk-12345
```

**Why This Breaks:**
1. VITE_ variables are embedded in the JavaScript bundle
2. Anyone can see them in browser DevTools
3. Secrets are exposed to all users

**The Fix:** Never prefix secrets with `VITE_`. Keep them server-side only.

## Accessing Variables

```typescript
// src/lib/api.ts
const API_BASE_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? '' : 'http://localhost:8000');
```

### Built-in Variables

| Variable | Type | Description |
|----------|------|-------------|
| `import.meta.env.MODE` | string | `'development'` or `'production'` |
| `import.meta.env.PROD` | boolean | `true` in production build |
| `import.meta.env.DEV` | boolean | `true` in development |
| `import.meta.env.BASE_URL` | string | Base URL from `base` config |

## Build-time vs Runtime

Vite replaces `import.meta.env.*` at build time:

```typescript
// Source code
if (import.meta.env.DEV) {
  console.log("Debug mode");
}

// After production build (dead code eliminated)
// The if block is completely removed
```

### WARNING: Dynamic Environment Access

**The Problem:**

```typescript
// BAD - Dynamic key access doesn't work
const key = "VITE_API_URL";
const value = import.meta.env[key];  // Always undefined!
```

**Why This Breaks:** Vite statically replaces `import.meta.env.VITE_*` at build time. Dynamic access is not analyzed.

**The Fix:**

```typescript
// GOOD - Static access
const value = import.meta.env.VITE_API_URL;
```

## Docker Build Args

Environment variables at build time use Docker ARG:

```dockerfile
# Dockerfile
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION

RUN npm run build
```

```bash
# Build with version
docker build --build-arg APP_VERSION=1.2.3 .
```

```typescript
// src/components/layout/Sidebar.tsx
const appVersion = import.meta.env.VITE_APP_VERSION || 'dev';
```

## Common Patterns

### Conditional API Base URL

```typescript
// Empty string in production = same origin (FastAPI serves frontend)
const API_BASE_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? '' : 'http://localhost:8000');
```

### Feature Flags

```typescript
// .env.development
VITE_ENABLE_DEBUG_PANEL=true

// Component
{import.meta.env.VITE_ENABLE_DEBUG_PANEL === 'true' && <DebugPanel />}
```

### Type Safety for Environment Variables

```typescript
// src/vite-env.d.ts (create if needed)
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_APP_VERSION: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

## Related Skills

- See the **typescript** skill for type declarations