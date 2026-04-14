"use client";

import { useRef, useState, useEffect } from "react";
import { Search, X } from "lucide-react";

interface SearchInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?: string;
}

export default function SearchInput({
  value,
  onChange,
  placeholder = "Search...",
  debounceMs = 0,
  className = "",
}: SearchInputProps) {
  const [internal, setInternal] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { setInternal(value); }, [value]);

  const handleChange = (v: string) => {
    setInternal(v);
    if (debounceMs > 0) {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => onChange(v), debounceMs);
    } else {
      onChange(v);
    }
  };

  return (
    <div className={className} style={{ position: "relative", width: "100%", maxWidth: 360 }}>
      <Search size={16} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
      <input
        type="text"
        className="form-input"
        style={{ paddingLeft: 36, paddingRight: internal ? 36 : 12 }}
        placeholder={placeholder}
        value={internal}
        onChange={(e) => handleChange(e.target.value)}
      />
      {internal && (
        <button
          onClick={() => handleChange("")}
          style={{
            position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
            background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)",
            padding: 4, display: "flex",
          }}
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
