"use client";

import { TriangleAlert } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { API_BASE_URL } from "@/lib/api";
import { buildFunnelStages, buildMetricCards } from "@/lib/metrics";
import { useCompanies } from "@/lib/useCompanies";
import { rangeLabel, useDashboardStats } from "@/lib/useDashboardStats";

import { ActivityFeed } from "./ActivityFeed";
import { BudgetCard } from "./BudgetCard";
import { DashboardHeader } from "./DashboardHeader";
import { DashboardSkeleton } from "./DashboardSkeleton";
import { DecisionList } from "./DecisionList";
import { MetricCards } from "./MetricCards";
import { ResponseChart } from "./ResponseChart";
import { SalesFlow } from "./SalesFlow";

export function DashboardOverview() {
  const {
    data,
    error,
    isLoading,
    isRefreshing,
    lastUpdatedAt,
    days,
    setDays,
    refresh,
  } = useDashboardStats();
  const review = useCompanies({ limit: 10, status: "review" });

  const refreshAll = () => {
    refresh();
    review.refresh();
  };

  return (
    <div className="space-y-5">
      <DashboardHeader
        lastUpdatedAt={lastUpdatedAt}
        isRefreshing={isRefreshing}
        days={days}
        daily={data?.daily ?? []}
        onDaysChange={setDays}
        onRefresh={refreshAll}
      />

      {/* Elimizde veri varken hata olursa panel boşaltılmaz; uyarı şeridi eklenir. */}
      {error && data ? (
        <p className="flex items-center gap-2 rounded-xl border border-accent-line bg-accent-soft px-3 py-2 text-[11px] text-accent">
          <TriangleAlert className="size-3.5 shrink-0" />
          Veriler yenilenemedi, en son alınan değerler gösteriliyor. {error}
        </p>
      ) : null}

      {isLoading ? <DashboardSkeleton /> : null}

      {!isLoading && error && !data ? (
        <ConnectionError message={error} onRetry={refresh} />
      ) : null}

      {data ? (
        <div className="space-y-4">
          <MetricCards cards={buildMetricCards(data)} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)]">
            <div className="space-y-4">
              <SalesFlow stages={buildFunnelStages(data)} />
              <ResponseChart
                daily={data.daily ?? []}
                title={rangeLabel(days)}
              />
            </div>

            <DecisionList companies={review.data?.items ?? []} />

            <ActivityFeed aiStatus={data.ai_status} />

            <BudgetCard />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ConnectionError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card className="p-8">
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 text-center">
        <span className="flex size-9 items-center justify-center rounded-xl bg-danger-soft text-danger">
          <TriangleAlert className="size-4" strokeWidth={2} />
        </span>
        <h2 className="text-[14px] font-semibold text-ink">
          Panel verileri yüklenemedi
        </h2>
        <p className="text-[12px] leading-relaxed text-ink-soft">{message}</p>
        <code className="rounded-lg bg-line-soft px-2 py-1 text-[11px] text-ink-soft">
          uvicorn api.index:app --reload
        </code>
        <p className="text-[11px] text-ink-muted">
          Beklenen adres: {API_BASE_URL}/api/dashboard-stats
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-lg bg-brand px-3.5 py-1.5 text-[12px] font-medium text-on-brand transition-colors hover:bg-brand-light"
        >
          Tekrar dene
        </button>
      </div>
    </Card>
  );
}
