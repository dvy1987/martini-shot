import { describe, expect, it } from "vitest";

import {
  clearSlateSeen,
  isSlateSeen,
  markSlateSeen,
  slateForRoute,
  slateStorageKey,
} from "@/lib/slates";

function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => [...store.keys()][index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };
}

describe("slate memory", () => {
  it("uses pc.seen.* keys and treats only '1' as dismissed", () => {
    const storage = memoryStorage();
    expect(slateStorageKey("welcome")).toBe("pc.seen.welcome");
    expect(isSlateSeen("welcome", storage)).toBe(false);
    markSlateSeen("welcome", storage);
    expect(isSlateSeen("welcome", storage)).toBe(true);
    clearSlateSeen("welcome", storage);
    expect(isSlateSeen("welcome", storage)).toBe(false);
  });

  it("maps routes to the charter slate for that surface", () => {
    expect(slateForRoute("/")).toBe("welcome");
    expect(slateForRoute("/approvals")).toBe("accounting");
    expect(slateForRoute("/suggestions")).toBe("accounting");
    expect(slateForRoute("/reports")).toBe("dailies");
    expect(slateForRoute("/analytics")).toBe("investigation");
  });
});
