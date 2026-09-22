"use client";

import { usePathname } from "next/navigation";
import { ChevronRight, Pause, Search } from "lucide-react";

import { findNavItem } from "./nav";

export function Topbar() {
  const pathname = usePathname();
  const section = findNavItem(pathname)?.label ?? "Genel Bakış";

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-canvas px-8">
      <nav aria-label="Konum" className="flex items-center gap-1 text-[12px]">
        <span className="text-ink-soft">{section}</span>
        <ChevronRight className="size-3 text-ink-muted" />
        <span className="text-ink-muted">Ana sayfa</span>
      </nav>

      <div className="relative w-full max-w-[320px]">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-ink-muted" />
        <input
          type="search"
          placeholder="Ara..."
          aria-label="Ara"
          className="h-8 w-full rounded-full border border-line bg-surface pr-3 pl-9 text-[12px] text-ink placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
        />
      </div>

      <div className="ml-auto flex items-center gap-2.5">
        <span className="rounded-full border border-accent-line bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent">
          Konsept • Örnek veri
        </span>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-brand-deep"
        >
          <Pause className="size-3 fill-current" />
          Sistemi durdur
        </button>
      </div>
    </header>
  );
}
