"use client";

import useSWR from "swr";

import {
  ApiError,
  fetchCompanies,
  type CompanyListResponse,
  type CompanyQuery,
} from "./api";

interface CompaniesState {
  data: CompanyListResponse | null;
  error: string | null;
  isLoading: boolean;
  isRefreshing: boolean;
  refresh: () => void;
}

export function useCompanies(query: CompanyQuery): CompaniesState {
  const key = [
    "companies",
    query.limit ?? null,
    query.offset ?? null,
    query.search ?? null,
    query.status ?? null,
    query.qualifiedOnly ?? false,
  ] as const;

  const { data, error, isLoading, isValidating, mutate } = useSWR<
    CompanyListResponse,
    unknown
  >(key, () => fetchCompanies(query), {
    refreshInterval: 20_000,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error instanceof ApiError ? error.message : error ? "Beklenmeyen bir hata oluştu." : null,
    isLoading,
    isRefreshing: isValidating,
    refresh: () => void mutate(),
  };
}
