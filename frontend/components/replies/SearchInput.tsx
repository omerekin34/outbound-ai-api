"use client";

import { Search, X } from "lucide-react";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}

export function SearchInput({ value, onChange, placeholder }: SearchInputProps) {
  return (
    <div className="relative">
      <Search
        className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
        strokeWidth={2}
      />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-line bg-surface py-1.5 pr-8 pl-8 text-[12px] text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none sm:w-64"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Aramayı temizle"
          className="absolute top-1/2 right-2 -translate-y-1/2 text-ink-muted transition-colors hover:text-ink"
        >
          <X className="size-3.5" strokeWidth={2} />
        </button>
      ) : null}
    </div>
  );
}
