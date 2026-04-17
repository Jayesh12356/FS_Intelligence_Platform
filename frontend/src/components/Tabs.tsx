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
}

export default function Tabs({
  items,
  active,
  onChange,
  className = "",
  "aria-label": ariaLabel,
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
            aria-controls={`tabpanel-${item.key}`}
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
