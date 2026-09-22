"use client";

import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle: string;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  children?: ReactNode;
}

/** Genel Bakış başlığıyla aynı yapı: başlık + açıklama + sağda eylemler. */
export function PageHeader({
  title,
  subtitle,
  isRefreshing = false,
  onRefresh,
  children,
}: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-ink">
          {title}
        </h1>
        <p className="mt-1 text-[13px] text-ink-soft">{subtitle}</p>
      </div>

      <div className="flex items-center gap-2">
        {children}
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand"
          >
            <RefreshCw
              className={`size-3.5 ${isRefreshing ? "animate-spin" : ""}`}
              strokeWidth={2}
            />
            Yenile
          </button>
        ) : null}
      </div>
    </div>
  );
}
