# Hot Module Replacement Reference

## Contents
- HMR Basics
- React Fast Refresh
- Debugging HMR Issues
- State Preservation
- Common Problems

## HMR Basics

Vite uses native ES modules for instant HMR. Changes reflect in <100ms without full page reload.

```typescript
// vite.config.ts - HMR is enabled by default
server: {
  host: "::",
  port: 8080,
  hmr: {
    // Override WebSocket settings if needed
    host: 'localhost',
    port: 8080,
  },
}
```

## React Fast Refresh

@vitejs/plugin-react-swc enables React Fast Refresh:

- Component state preserved on edit
- Hooks state preserved
- Only changed components re-render

### Rules for Fast Refresh

1. **Export only React components** from component files
2. **Use PascalCase** for component names
3. **Avoid anonymous default exports**

```typescript
// GOOD - Fast Refresh works
export const BookCard = ({ book }: BookCardProps) => {
  return <div>{book.title}</div>;
};

// BAD - Breaks Fast Refresh
export default ({ book }) => <div>{book.title}</div>;
```

### WARNING: Mixed Exports Break Fast Refresh

**The Problem:**

```typescript
// BAD - Component + utility in same file
export const BookCard = () => <div>Card</div>;
export const formatPrice = (price: number) => `$${price}`;
```

**Why This Breaks:** Fast Refresh can't determine if the file is a component module. It falls back to full page reload.

**The Fix:** Keep components and utilities in separate files:

```typescript
// src/components/BookCard.tsx
export const BookCard = () => <div>Card</div>;

// src/lib/utils.ts
export const formatPrice = (price: number) => `$${price}`;
```

## Debugging HMR Issues

### Check Browser Console

```
[vite] connected.
[vite] hot updated: /src/components/BookCard.tsx
```

If you see errors:
```
[vite] server connection lost. Polling for restart...
```

### Common Causes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Full reload on every save | Mixed exports | Separate components from utilities |
| "Connection lost" | Wrong host/port | Check `server.hmr` config |
| No updates | File not imported | Verify import chain |
| State lost | Component remount | Check Fast Refresh rules |

### Network Tab Debugging

1. Open DevTools → Network
2. Filter by WS (WebSocket)
3. Look for connection to `ws://localhost:8080/`
4. Check for 404 or connection errors

## State Preservation

Fast Refresh preserves:
- `useState` values
- `useRef` values
- Class component state

Fast Refresh resets:
- Module-level variables
- `useEffect` cleanup and re-run
- Context providers (consumers re-render)

```typescript
// State preserved on edit
const [count, setCount] = useState(0);

// Re-runs on every edit
useEffect(() => {
  console.log("Effect ran");
}, []);
```

### Force Full Reload

Add this comment to force full reload:

```typescript
// @refresh reset
export const MyComponent = () => { ... };
```

## Common Problems

### Docker/Container HMR

When running in Docker, configure HMR for container networking:

```typescript
server: {
  host: "::",
  port: 8080,
  watch: {
    usePolling: true,  // Required for Docker volumes
  },
}
```

### WSL2 HMR

```typescript
server: {
  watch: {
    usePolling: true,
    interval: 100,
  },
}
```

### Proxy/Firewall Issues

If behind a reverse proxy:

```typescript
server: {
  hmr: {
    clientPort: 443,  // Match your external port
    protocol: 'wss',  // Use secure WebSocket
  },
}
```

## ESLint Integration

The project uses eslint-plugin-react-refresh:

```javascript
// eslint.config.js
{
  plugins: {
    "react-refresh": reactRefresh,
  },
  rules: {
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true }
    ],
  },
}
```

This warns when exports break Fast Refresh.

## Related Skills

- See the **react** skill for component patterns
- See the **typescript** skill for ESLint configuration