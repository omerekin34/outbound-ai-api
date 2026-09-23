import { ArrowRight, Calendar, ChevronDown, RefreshCw } from "lucide-react";

interface DashboardHeaderProps {
  lastUpdatedAt: Date | null;
  isRefreshing: boolean;
  onRefresh: () => void;
}

export function DashboardHeader({
  isRefreshing,
  onRefresh,
}: DashboardHeaderProps) {
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
          title="Verileri yenile"
          className="flex size-8 items-center justify-center rounded-lg border border-line bg-surface text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
        >
          <RefreshCw
            className={`size-3.5 ${isRefreshing ? "animate-spin" : ""}`}
            strokeWidth={2}
          />
          <span className="sr-only">Verileri yenile</span>
        </button>

        <button
          type="button"
          className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-ink-muted"
        >
          <Calendar className="size-3.5 text-ink-muted" strokeWidth={2} />
          Son 7 gün
          <ChevronDown className="size-3 text-ink-muted" />
        </button>

        <button
          type="button"
          className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-brand-deep"
        >
          Günlük özeti aç
          <ArrowRight className="size-3.5" />
        </button>
      </div>
    </div>
  );
}
