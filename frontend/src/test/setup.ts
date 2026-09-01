// Vitest DOM setup: jest-dom matchers. jsdom environment is configured in vite.config.ts.
import "@testing-library/jest-dom/vitest";

// C-1.3 test-environment fixture: under Node >=22 without --localstorage-file,
// jsdom's localStorage does not initialize, so component tests that touch
// window.localStorage directly get `undefined`. Shim a minimal in-memory
// Storage (test-only; the app itself always runs in a real browser origin).
if (typeof window.localStorage === "undefined") {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string): string | null => store.get(key) ?? null,
      setItem: (key: string, value: string): void => {
        store.set(key, String(value));
      },
      removeItem: (key: string): void => {
        store.delete(key);
      },
      clear: (): void => {
        store.clear();
      },
    },
  });
}
