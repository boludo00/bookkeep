# Vite Configuration Reference

## Contents
- Base Configuration
- Path Aliases
- Server Configuration
- Plugin Configuration
- Build Configuration
- Common Errors

## Base Configuration

The project uses function-style config for mode access:

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
  },
}));
```

## Path Aliases

Path aliases must be configured in BOTH vite.config.ts and tsconfig.json:

```typescript
// vite.config.ts
resolve: {
  alias: {
    "@": path.resolve(__dirname, "./src"),
  },
}
```

```json
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### WARNING: Mismatched Path Aliases

**The Problem:**

```typescript
// vite.config.ts has "@" -> "./src"
// tsconfig.json has "@" -> "./source"  // MISMATCH!

import { Button } from "@/components/ui/button";
// TypeScript: resolves to ./source/components/ui/button
// Vite: resolves to ./src/components/ui/button
```

**Why This Breaks:**
1. TypeScript shows errors for correct imports
2. IDE navigation goes to wrong files
3. Build succeeds but runtime fails

**The Fix:** Always keep both files in sync.

## Server Configuration

```typescript
server: {
  host: "::",      // Listen on all interfaces (required for Docker)
  port: 8080,      // Frontend dev port
  strictPort: true, // Fail if port is taken (optional)
  proxy: {         // Proxy API calls to backend (alternative to CORS)
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

## Plugin Configuration

### SWC Plugin (Current)

```typescript
import react from "@vitejs/plugin-react-swc";

plugins: [react()]  // Uses SWC - faster than Babel
```

### WARNING: Mixing Babel and SWC

**The Problem:**

```typescript
// WRONG - Using Babel plugin with SWC
import react from "@vitejs/plugin-react";  // Babel version
```

**Why This Breaks:**
1. Slower builds (Babel is 10-20x slower than SWC)
2. Larger node_modules
3. Different transform behavior

**The Fix:** Use `@vitejs/plugin-react-swc` consistently.

## Build Configuration

```typescript
build: {
  outDir: "dist",
  sourcemap: mode === "development",  // Optional: sourcemaps for debugging
  rollupOptions: {
    output: {
      manualChunks: {                 // Optional: custom chunking
        vendor: ['react', 'react-dom'],
      },
    },
  },
}
```

## Common Errors

### "Failed to resolve import"

Check path alias configuration in both files.

### "Port 8080 is already in use"

```bash
# Find and kill process
lsof -i :8080
kill -9 <PID>
```

### HMR not working

1. Check browser console for WebSocket errors
2. Verify `server.host` allows your network interface
3. Check firewall rules

## Related Skills

- See the **typescript** skill for tsconfig.json patterns
- See the **react** skill for plugin compatibility