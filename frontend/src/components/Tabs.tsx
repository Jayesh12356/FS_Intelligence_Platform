"use client";

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
}

export default function Tabs({ items, active, onChange, className = "" }: TabsProps) {
  return (
    <div className={`tabs ${className}`}>
      {items.map((item) => (
        <button
          key={item.key}
          className={`tab ${active === item.key ? "active" : ""}`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
          {item.count !== undefined && (
            <span style={{ opacity: 0.6, marginLeft: 4, fontSize: "0.75rem" }}>
              {item.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
