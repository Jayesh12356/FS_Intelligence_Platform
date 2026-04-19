import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// ---- jsdom polyfills --------------------------------------------------------
// jsdom ships without these browser APIs that framer-motion / headlessui /
// our own lazy-render components rely on. Installing stubs once at setup
// time keeps every test harness behaving like a real browser.
if (typeof globalThis.IntersectionObserver === "undefined") {
  class IntersectionObserverStub {
    constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
    disconnect() {}
    observe() {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
    unobserve() {}
    root = null;
    rootMargin = "";
    thresholds = [] as ReadonlyArray<number>;
  }
  // Cast through unknown to satisfy the strict constructor signature.
  globalThis.IntersectionObserver = IntersectionObserverStub as unknown as typeof IntersectionObserver;
}

if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    constructor(_cb: ResizeObserverCallback) {}
    disconnect() {}
    observe() {}
    unobserve() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

afterEach(() => {
  cleanup();
});
