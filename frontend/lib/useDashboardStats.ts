"use client";

import useSWR from "swr";

import {
  ApiError,
  fetchDashboardStats,
  type DashboardStatsResponse,
} from "./api";

/** Aktivite akışının canlı kalması için varsayılan yoklama aralığı. */
const DEFAULT_POLL_MS = 20_000;

const STATS_KEY = "dashboard-stats";

interface UseDashboardStats {
  data: DashboardStatsResponse | null;
  error: string | null;
  /** Yalnızca ilk yüklemede true; yenilemelerde iskelet tekrar gösterilmez. */
  isLoading: boolean;
  isRefreshing: boolean;
  /** Backend'in yanıtı ürettiği an (`generated_at`). */
  lastUpdatedAt: Date | null;
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
  const { data, error, isLoading, isValidating, mutate } = useSWR<
    DashboardStatsResponse,
    unknown
  >(STATS_KEY, () => fetchDashboardStats(), {
    refreshInterval: pollMs,
    // Bağlantı hatasında panel boşalmasın, son değerler ekranda kalsın.
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error ? toMessage(error) : null,
    isLoading,
    isRefreshing: isValidating,
    lastUpdatedAt: data ? new Date(data.generated_at) : null,
    refresh: () => void mutate(),
  };
}

function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Beklenmeyen bir hata oluştu.";
}
