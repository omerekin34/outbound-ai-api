"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChevronRight, Pause, Play } from "lucide-react";
import useSWR from "swr";

import {
  ApiError,
  fetchPipelineStatus,
  setPipelinePaused,
  type PipelineStatus,
} from "@/lib/api";

import { CompanySearch } from "./CompanySearch";
import { findNavItem } from "./nav";

export function Topbar() {
  const pathname = usePathname();
  const section = findNavItem(pathname) ?? findNavItem("/")!;
  const [busy, setBusy] = useState(false);

  const { data: pipeline, mutate } = useSWR<PipelineStatus, unknown>(
    "pipeline-status",
    () => fetchPipelineStatus(),
    { refreshInterval: 8_000, keepPreviousData: true },
  );

  async function togglePipeline() {
    if (busy) return;
    setBusy(true);
    try {
      const next = await setPipelinePaused(!(pipeline?.paused ?? false));
      await mutate(next, { revalidate: false });
    } catch (error) {
      window.alert(
        error instanceof ApiError
          ? error.message
          : "Sistem durumu değiştirilemedi.",
      );
    } finally {
      setBusy(false);
    }
  }

  const paused = pipeline?.paused ?? false;
  const pending = pipeline?.pending_jobs ?? 0;
  const statusLabel = paused
    ? "Duraklatıldı"
    : pending > 0
      ? `Kuyrukta ${pending}`
      : "Canlı";

  return (
    <header className="relative z-20 flex h-14 shrink-0 items-center gap-6 border-b border-line bg-canvas px-8">
      <nav aria-label="Konum" className="flex items-center gap-1 text-[12px]">
        <Link href={section.href} className="text-ink-soft hover:text-ink">
          {section.label}
        </Link>
        <ChevronRight className="size-3 text-ink-muted" />
        <Link href="/" className="text-ink-muted hover:text-ink">
          Ana sayfa
        </Link>
      </nav>

      <CompanySearch />

      <div className="ml-auto flex items-center gap-2.5">
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            paused
              ? "border-accent-line bg-accent-soft text-accent"
              : "border-brand/30 bg-brand-soft text-brand"
          }`}
        >
          {statusLabel}
        </span>
        <button
          type="button"
          onClick={() => void togglePipeline()}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-danger hover:text-danger disabled:opacity-50"
        >
          {paused ? (
            <Play className="size-3 fill-current" />
          ) : (
            <Pause className="size-3 fill-current" />
          )}
          {paused ? "Sistemi başlat" : "Sistemi durdur"}
        </button>
      </div>
    </header>
  );
}
