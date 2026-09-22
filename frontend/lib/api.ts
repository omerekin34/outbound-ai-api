/**
 * FastAPI backend sözleşmesi.
 *
 * Tipler `api/schemas.py` içindeki Pydantic modelleriyle birebir eşleşir.
 * Backend'de bir alan değişirse burayı da güncelleyin.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type AiState = "working" | "idle" | "stalled" | "error";
export type ActivityStatus = "running" | "success" | "failed" | "skipped";

export interface DashboardStats {
  total_companies: number;
  researched_companies: number;
  pending_companies: number;
  analyzed_companies: number;
  companies_added_today: number;
  companies_added_last_7_days: number;
  total_contacts: number;
  average_overall_score: number | null;
  high_intent_companies: number;
  positive_replies: number;
  unread_replies: number;
}

export interface Activity {
  id: number;
  event_type: string;
  status: ActivityStatus;
  message: string;
  company_id: string | null;
  company_name: string | null;
  detail: Record<string, unknown> | null;
  duration_ms: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface AiStatus {
  state: AiState;
  headline: string;
  current: Activity | null;
  recent: Activity[];
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface IndustryCount {
  industry: string;
  count: number;
}

export interface DashboardStatsResponse {
  generated_at: string;
  stats: DashboardStats;
  ai_status: AiStatus;
  status_breakdown: StatusCount[];
  top_industries: IndustryCount[];
}

/** Kullanıcıya gösterilebilir hata mesajı taşıyan istek hatası. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      signal,
      headers: { Accept: "application/json" },
      // Panel her zaman canlı veri göstermeli.
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `API'ye ulaşılamadı (${API_BASE_URL}). FastAPI sunucusunun çalıştığından emin olun.`,
    );
  }

  if (!response.ok) {
    // FastAPI hataları `{ "detail": "..." }` biçiminde döner.
    let detail = `İstek başarısız (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Gövde JSON değilse varsayılan mesajla devam et.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export function fetchDashboardStats(
  signal?: AbortSignal,
): Promise<DashboardStatsResponse> {
  return request<DashboardStatsResponse>("/api/dashboard-stats", signal);
}

/* --- Gelen kutusu / Fırsatlar --------------------------------------------- */

/** `api/models.py` içindeki `Interaction.CLASS_*` değerleriyle eşleşir. */
export type Classification =
  | "positive"
  | "meeting_request"
  | "question"
  | "neutral"
  | "negative"
  | "unsubscribe"
  | "auto_reply";

export interface Reply {
  id: number;

  company_id: string | null;
  company_name: string | null;
  company_domain: string | null;
  company_industry: string | null;
  company_city: string | null;

  contact_id: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;

  subject: string | null;
  /** Yanıtın birebir metni. */
  body: string;
  /** Tabloda gösterilen tek satırlık önizleme. */
  snippet: string;

  classification: Classification | string | null;
  confidence: number | null;
  ai_summary: string | null;
  ai_next_action: string | null;

  channel: string;
  is_read: boolean;
  received_at: string;
  overall_score: number | null;
}

export interface ClassificationCount {
  classification: string;
  count: number;
}

export interface InboxResponse {
  items: Reply[];
  /** Seçili filtrelere uyan yanıt sayısı. */
  total: number;
  limit: number;
  offset: number;
  /** Filtresiz toplam; üst sayaçlar ve "Tümü" çipi bunu kullanır. */
  inbound_total: number;
  unread_count: number;
  positive_count: number;
  classification_breakdown: ClassificationCount[];
}

export interface OpportunitiesResponse {
  items: Reply[];
  total: number;
  limit: number;
  offset: number;
  unique_companies: number;
  average_score: number | null;
}

export interface InboxQuery {
  limit?: number;
  offset?: number;
  classification?: string | null;
  unreadOnly?: boolean;
  search?: string | null;
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function fetchInbox(
  query: InboxQuery = {},
  signal?: AbortSignal,
): Promise<InboxResponse> {
  const path = `/api/inbox${buildQuery({
    limit: query.limit,
    offset: query.offset,
    classification: query.classification,
    unread_only: query.unreadOnly ? true : undefined,
    search: query.search,
  })}`;
  return request<InboxResponse>(path, signal);
}

export interface DecisionMaker {
  id: string;
  company_id: string | null;
  company_name: string | null;
  company_domain: string | null;
  company_status: string | null;
  first_name: string | null;
  last_name: string | null;
  name: string | null;
  title: string | null;
  email: string | null;
  linkedin_url: string | null;
}

export interface ContactListResponse {
  items: DecisionMaker[];
  total: number;
  limit: number;
  offset: number;
}

export function fetchDecisionMakers(
  query: Pick<InboxQuery, "limit" | "offset" | "search"> = {},
  signal?: AbortSignal,
): Promise<ContactListResponse> {
  const path = `/api/contacts${buildQuery({
    limit: query.limit,
    offset: query.offset,
    search: query.search,
    qualified_only: true,
  })}`;
  return request<ContactListResponse>(path, signal);
}

export function fetchOpportunities(
  query: Pick<InboxQuery, "limit" | "offset" | "search"> = {},
  signal?: AbortSignal,
): Promise<OpportunitiesResponse> {
  const path = `/api/opportunities${buildQuery({
    limit: query.limit,
    offset: query.offset,
    search: query.search,
  })}`;
  return request<OpportunitiesResponse>(path, signal);
}

export interface ResearchAccepted {
  status: "accepted";
  message: string;
  domain: string;
  website: string;
  company_id: string;
}

export async function startResearch(domain: string): Promise<ResearchAccepted> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/research`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ domain }),
    });
  } catch {
    throw new ApiError(
      `API'ye ulaşılamadı (${API_BASE_URL}). FastAPI sunucusunun çalıştığından emin olun.`,
    );
  }

  if (!response.ok) {
    let detail = `İstek başarısız (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        const first = body.detail[0] as { msg?: string } | undefined;
        if (first?.msg) {
          detail = first.msg.replace(/^Value error,\s*/i, "");
        }
      }
    } catch {
      // Gövde JSON değilse varsayılan mesajla devam et.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as ResearchAccepted;
}

export async function markReplyRead(
  id: number,
  isRead: boolean,
): Promise<Reply> {
  const response = await fetch(
    `${API_BASE_URL}/api/inbox/${id}/read?is_read=${isRead}`,
    { method: "PATCH", headers: { Accept: "application/json" } },
  );

  if (!response.ok) {
    throw new ApiError(`Yanıt güncellenemedi (HTTP ${response.status}).`);
  }
  return (await response.json()) as Reply;
}
