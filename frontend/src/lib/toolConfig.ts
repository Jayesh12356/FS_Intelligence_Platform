"use client";

/**
 * Shared, reactive snapshot of `/api/orchestration/config`.
 *
 * The config tells every page which Document LLM provider is active
 * (``api`` | ``claude_code`` | ``cursor``) so Generate FS / Analyze /
 * Reverse FS can branch between the synchronous call and the
 * paste-per-action Cursor task flow.
 *
 * Call :func:`notifyToolConfigUpdated` after a successful
 * ``PUT /api/orchestration/config`` so mounted components re-render
 * immediately without waiting for a full page reload.
 */

import { useCallback, useEffect, useState } from "react";

import { getToolConfig, type ToolConfig } from "@/lib/api";

const TOOL_CONFIG_EVENT = "tool-config-updated";

let cachedConfig: ToolConfig | null = null;
let inFlightConfig: Promise<ToolConfig | null> | null = null;

async function fetchToolConfigOnce(): Promise<ToolConfig | null> {
  if (cachedConfig) return cachedConfig;
  if (inFlightConfig) return inFlightConfig;
  inFlightConfig = (async () => {
    try {
      const res = await getToolConfig();
      cachedConfig = res.data ?? null;
      return cachedConfig;
    } catch {
      return null;
    } finally {
      inFlightConfig = null;
    }
  })();
  return inFlightConfig;
}

export function notifyToolConfigUpdated(next?: ToolConfig): void {
  if (typeof window === "undefined") return;
  if (next) cachedConfig = next;
  else cachedConfig = null;
  window.dispatchEvent(new CustomEvent(TOOL_CONFIG_EVENT));
}

export function useToolConfig(): {
  config: ToolConfig | null;
  loading: boolean;
  refresh: () => Promise<void>;
} {
  const [config, setConfig] = useState<ToolConfig | null>(cachedConfig);
  const [loading, setLoading] = useState<boolean>(cachedConfig === null);

  const refresh = useCallback(async () => {
    cachedConfig = null;
    setLoading(true);
    const next = await fetchToolConfigOnce();
    setConfig(next);
    setLoading(false);
  }, []);

  useEffect(() => {
    let alive = true;
    if (!cachedConfig) {
      fetchToolConfigOnce().then((next) => {
        if (!alive) return;
        setConfig(next);
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
    const onUpdated = () => {
      if (!alive) return;
      setConfig(cachedConfig);
      if (!cachedConfig) {
        fetchToolConfigOnce().then((next) => {
          if (!alive) return;
          setConfig(next);
        });
      }
    };
    window.addEventListener(TOOL_CONFIG_EVENT, onUpdated);
    return () => {
      alive = false;
      window.removeEventListener(TOOL_CONFIG_EVENT, onUpdated);
    };
  }, []);

  return { config, loading, refresh };
}

/** Canonical lowercase name of the active Document LLM provider. */
export function normalizeProvider(p: string | null | undefined): string {
  return (p ?? "").trim().toLowerCase();
}

export function isCursorProvider(p: string | null | undefined): boolean {
  return normalizeProvider(p) === "cursor";
}
