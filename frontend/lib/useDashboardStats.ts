"use client";

import { useState } from "react";
import useSWR from "swr";

import {
  ApiError,
  fetchDashboardStats,
  type DashboardStatsResponse,
} from "./api";

/** Aktivite akışının canlı kalması için varsayılan yoklama aralığı. */
const DEFAULT_POLL_MS = 20_000;

export const RANGE_OPTIONS = [
  { days: 1, label: "Bugün" },
  { days: 7, label: "Son 7 gün" },
  { days: 14, label: "Son 14 gün" },
  { days: 30, label: "Son 30 gün" },
] as const;

export type RangeDays = (typeof RANGE_OPTIONS)[number]["days"];

export function rangeLabel(days: number): string {
  return RANGE_OPTIONS.find((option) => option.days === days)?.label ?? `Son ${days} gün`;
}

interface UseDashboardStats {
  data: DashboardStatsResponse | null;
  error: string | null;
  /** Yalnızca ilk yüklemede true; yenilemelerde iskelet tekrar gösterilmez. */
  isLoading: boolean;
  isRefreshing: boolean;
  /** Backend'in yanıtı ürettiği an (`generated_at`). */
  lastUpdatedAt: Date | null;
  days: RangeDays;
  setDays: (days: RangeDays) => void;
  refresh: () => void;
}

/**
 * Dashboard verisini SWR ile okur.
 *
 * SWR varsayılanları bu ekran için doğru davranışı zaten sağlıyor:
 * sekme arkaplandayken yoklama durur (`refreshWhenHidden: false`), sekmeye
 * geri dönüldüğünde veri yenilenir (`revalidateOnFocus`) ve aynı anahtarlı
 * istekler tekilleştirilir.
 */
export function useDashboardStats(pollMs = DEFAULT_POLL_MS): UseDashboardStats {
  const [days, setDays] = useState<RangeDays>(7);
  const [manualRefresh, setManualRefresh] = useState(false);
  const { data, error, isLoading, mutate } = useSWR<
    DashboardStatsResponse,
    unknown
  >(["dashboard-stats", days], () => fetchDashboardStats(days), {
    refreshInterval: pollMs,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error ? toMessage(error) : null,
    isLoading,
    isRefreshing: manualRefresh,
    lastUpdatedAt: data ? new Date(data.generated_at) : null,
    days,
    setDays,
    refresh: () => {
      setManualRefresh(true);
      void mutate().finally(() => setManualRefresh(false));
    },
  };
}

function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Beklenmeyen bir hata oluştu.";
}
