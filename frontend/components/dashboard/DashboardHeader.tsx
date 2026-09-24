"use client";

import { ArrowRight, Calendar, ChevronDown, RefreshCw, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { DailyCount } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { RANGE_OPTIONS, rangeLabel, type RangeDays } from "@/lib/useDashboardStats";

interface DashboardHeaderProps {
  lastUpdatedAt: Date | null;
  isRefreshing: boolean;
  days: RangeDays;
  daily: DailyCount[];
  onDaysChange: (days: RangeDays) => void;
  onRefresh: () => void;
}

export function DashboardHeader({
  lastUpdatedAt,
  isRefreshing,
  days,
  daily,
  onDaysChange,
  onRefresh,
}: DashboardHeaderProps) {
  const [rangeOpen, setRangeOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const rangeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!rangeOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!rangeRef.current?.contains(event.target as Node)) {
        setRangeOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRangeOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [rangeOpen]);

  const openSummary = () => {
    setSummaryOpen(true);
    document.getElementById("gunluk-ozet")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  };

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-ink">
          Satışın kontrolü sende.
        </h1>
        <p className="mt-1 text-[13px] text-ink-soft">
          AI rutin işleri yürütür. Sen yalnızca sınır dışı kararları yönetirsin.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          title={
            lastUpdatedAt
              ? `Verileri yenile · ${lastUpdatedAt.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`
              : "Verileri yenile"
          }
          className="flex size-8 items-center justify-center rounded-lg border border-line bg-surface text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
        >
          <RefreshCw
            className={`size-3.5 ${isRefreshing ? "animate-spin" : ""}`}
            strokeWidth={2}
          />
          <span className="sr-only">Verileri yenile</span>
        </button>

        <div className="relative" ref={rangeRef}>
          <button
            type="button"
            aria-haspopup="listbox"
            aria-expanded={rangeOpen}
            onClick={() => setRangeOpen((open) => !open)}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-ink-muted"
          >
            <Calendar className="size-3.5 text-ink-muted" strokeWidth={2} />
            {rangeLabel(days)}
            <ChevronDown className="size-3 text-ink-muted" />
          </button>
          {rangeOpen ? (
            <ul
              role="listbox"
              aria-label="Tarih aralığı"
              className="absolute right-0 z-20 mt-1 min-w-full overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-[0_8px_24px_rgba(22,36,31,0.12)]"
            >
              {RANGE_OPTIONS.map((option) => (
                <li key={option.days}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={option.days === days}
                    className={`flex w-full px-3 py-1.5 text-left text-[12px] ${
                      option.days === days
                      ? "bg-brand font-semibold text-on-brand"
                      : "text-ink hover:bg-line-soft"
                    }`}
                    onClick={() => {
                      onDaysChange(option.days);
                      setRangeOpen(false);
                    }}
                  >
                    {option.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <button
          type="button"
          onClick={openSummary}
          className="flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-[12px] font-medium text-on-brand transition-colors hover:bg-brand-light"
        >
          Günlük özeti aç
          <ArrowRight className="size-3.5" />
        </button>
      </div>

      {summaryOpen ? (
        <DailySummaryDialog
          days={days}
          daily={daily}
          onClose={() => setSummaryOpen(false)}
        />
      ) : null}
    </div>
  );
}

function DailySummaryDialog({
  days,
  daily,
  onClose,
}: {
  days: number;
  daily: DailyCount[];
  onClose: () => void;
}) {
  const titleId = useId();
  const analyzed = daily.reduce((sum, row) => sum + row.analyzed, 0);
  const replies = daily.reduce((sum, row) => sum + row.positive_replies, 0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/55 px-4 py-16"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-card border border-line bg-surface p-5 shadow-[0_16px_40px_rgba(22,36,31,0.16)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">
              Günlük özet
            </p>
            <h2
              id={titleId}
              className="mt-1 text-[16px] font-semibold tracking-tight text-ink"
            >
              {rangeLabel(days)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-line text-ink-soft hover:text-ink"
            aria-label="Kapat"
          >
            <X className="size-3.5" strokeWidth={2} />
          </button>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-line-soft bg-canvas px-3 py-2.5">
            <dt className="text-[11px] text-ink-muted">Analiz edilen</dt>
            <dd className="mt-0.5 text-[20px] font-semibold text-ink">
              {formatNumber(analyzed)}
            </dd>
          </div>
          <div className="rounded-xl border border-line-soft bg-canvas px-3 py-2.5">
            <dt className="text-[11px] text-ink-muted">Olumlu yanıt</dt>
            <dd className="mt-0.5 text-[20px] font-semibold text-ink">
              {formatNumber(replies)}
            </dd>
          </div>
        </dl>

        <ul className="mt-4 max-h-64 divide-y divide-line-soft overflow-y-auto rounded-xl border border-line-soft">
          {daily.length === 0 ? (
            <li className="px-3 py-6 text-center text-[12px] text-ink-soft">
              Bu aralıkta günlük kayıt yok.
            </li>
          ) : (
            daily.map((row) => (
              <li
                key={row.date}
                className="flex items-center justify-between gap-3 px-3 py-2 text-[12px]"
              >
                <span className="text-ink">{row.label}</span>
                <span className="text-ink-soft">
                  {formatNumber(row.analyzed)} analiz · {formatNumber(row.positive_replies)} yanıt
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
