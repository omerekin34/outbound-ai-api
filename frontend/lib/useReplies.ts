"use client";

import useSWR from "swr";

import {
  ApiError,
  fetchDecisionMakers,
  fetchInbox,
  fetchOpportunities,
  type ContactListResponse,
  type InboxQuery,
  type InboxResponse,
  type OpportunitiesResponse,
} from "./api";

/** Yeni yanıtlar için yoklama aralığı. */
const DEFAULT_POLL_MS = 30_000;

interface RepliesState<T> {
  data: T | null;
  error: string | null;
  /** Yalnızca ilk yüklemede true; filtre değişiminde iskelet tekrar gelmez. */
  isLoading: boolean;
  isRefreshing: boolean;
  refresh: () => void;
}

function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Beklenmeyen bir hata oluştu.";
}

export function useInbox(
  query: InboxQuery,
  pollMs = DEFAULT_POLL_MS,
): RepliesState<InboxResponse> {
  // Anahtar filtreleri içerir: filtre değişince SWR yeni istek atar ama
  // `keepPreviousData` sayesinde eski liste ekranda kalır.
  const key = [
    "inbox",
    query.limit ?? null,
    query.offset ?? null,
    query.classification ?? null,
    query.unreadOnly ?? false,
    query.search ?? null,
  ] as const;

  const { data, error, isLoading, isValidating, mutate } = useSWR<
    InboxResponse,
    unknown
  >(key, () => fetchInbox(query), {
    refreshInterval: pollMs,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error ? toMessage(error) : null,
    isLoading,
    isRefreshing: isValidating,
    refresh: () => void mutate(),
  };
}

export function useOpportunities(
  query: Pick<InboxQuery, "limit" | "offset" | "search">,
  pollMs = DEFAULT_POLL_MS,
): RepliesState<OpportunitiesResponse> {
  const key = [
    "opportunities",
    query.limit ?? null,
    query.offset ?? null,
    query.search ?? null,
  ] as const;

  const { data, error, isLoading, isValidating, mutate } = useSWR<
    OpportunitiesResponse,
    unknown
  >(key, () => fetchOpportunities(query), {
    refreshInterval: pollMs,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error ? toMessage(error) : null,
    isLoading,
    isRefreshing: isValidating,
    refresh: () => void mutate(),
  };
}

export function useDecisionMakers(
  query: Pick<InboxQuery, "limit" | "offset" | "search">,
  pollMs = DEFAULT_POLL_MS,
): RepliesState<ContactListResponse> {
  const key = [
    "contacts",
    query.limit ?? null,
    query.offset ?? null,
    query.search ?? null,
  ] as const;

  const { data, error, isLoading, isValidating, mutate } = useSWR<
    ContactListResponse,
    unknown
  >(key, () => fetchDecisionMakers(query), {
    refreshInterval: pollMs,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    error: error ? toMessage(error) : null,
    isLoading,
    isRefreshing: isValidating,
    refresh: () => void mutate(),
  };
}
