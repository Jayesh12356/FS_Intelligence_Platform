"use client";

import { useRef } from "react";

interface TabItem {
  key: string;
  label: string;
  count?: number;
}

interface TabsProps {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
  "aria-label"?: string;
  /**
   * Optional map of `item.key -> existing element id` used to populate
   * each tab's ``aria-controls``. We *only* emit ``aria-controls`` when
   * a matching id is provided — pointing the attribute at a non-existent
   * id is a critical axe violation (`aria-valid-attr-value`), so the
   * default behaviour drops the attribute entirely. Pages that render
   * their content directly via the activeKey (the common case here) do
   * not need to wire this up.
   */
  panelIds?: Record<string, string | undefined>;
}

export default function Tabs({
  items,
  active,
  onChange,
  className = "",
  "aria-label": ariaLabel,
  panelIds,
}: TabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const focusIndex = (idx: number) => {
    const target = refs.current[idx];
    if (target) {
      target.focus();
      onChange(items[idx].key);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
    const count = items.length;
    if (count === 0) return;
    switch (e.key) {
      case "ArrowRight":
        e.preventDefault();
        focusIndex((idx + 1) % count);
        break;
      case "ArrowLeft":
        e.preventDefault();
        focusIndex((idx - 1 + count) % count);
        break;
      case "Home":
        e.preventDefault();
        focusIndex(0);
        break;
      case "End":
        e.preventDefault();
        focusIndex(count - 1);
        break;
      default:
        break;
    }
  };

  return (
    <div className={`tabs ${className}`} role="tablist" aria-label={ariaLabel}>
      {items.map((item, idx) => {
        const isActive = active === item.key;
        return (
          <button
            key={item.key}
            ref={(el) => {
              refs.current[idx] = el;
            }}
            role="tab"
            type="button"
            aria-selected={isActive}
            aria-controls={panelIds?.[item.key] || undefined}
            id={`tab-${item.key}`}
            tabIndex={isActive ? 0 : -1}
            className={`tab ${isActive ? "active" : ""}`}
            onClick={() => onChange(item.key)}
            onKeyDown={(e) => onKeyDown(e, idx)}
          >
            {item.label}
            {item.count !== undefined && (
              <span style={{ opacity: 0.6, marginLeft: 4, fontSize: "0.75rem" }}>
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
