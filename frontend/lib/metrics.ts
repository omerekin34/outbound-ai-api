import {
  Ban,
  Building2,
  CalendarClock,
  Hourglass,
  Mail,
  MailOpen,
  Sparkles,
  Target,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import type { Activity, DashboardStatsResponse } from "./api";

/**
 * Tasarımdaki kartların hangi backend alanından beslendiği burada tanımlanır.
 * Sahte / örnek sayı yok — her kart Neon'dan gelen bir sayaçtır.
 */
export interface MetricCard {
  key: string;
  label: string;
  value: number;
  icon: LucideIcon;
  tone: "brand" | "accent";
  delta: number | null;
  caption: string;
  provisional: boolean;
  href?: string;
}

export function buildMetricCards(data: DashboardStatsResponse): MetricCard[] {
  const { stats } = data;

  return [
    {
      key: "analyzed",
      label: "Araştırılan şirket",
      value: stats.analyzed_companies,
      icon: Building2,
      tone: "brand",
      delta: stats.companies_added_last_7_days,
      caption: "AI analizi tamamlanan",
      provisional: false,
      href: "/sirketler",
    },
    {
      key: "suitable",
      label: "Uygun",
      value: stats.suitable_companies,
      icon: Target,
      tone: "brand",
      delta: null,
      caption: "qualified / high priority",
      provisional: false,
      href: "/sirketler?filter=qualified",
    },
    {
      key: "contacts",
      label: "Karar verici",
      value: stats.total_contacts,
      icon: UserRound,
      tone: "brand",
      delta: null,
      caption: "Apollo’dan kaydedilen kişiler",
      provisional: false,
      href: "/firsatlar",
    },
    {
      key: "pending",
      label: "Karar bekleyen",
      value: stats.pending_companies + (stats.review_companies ?? 0),
      icon: Hourglass,
      tone: "accent",
      delta: null,
      caption: "Henüz puanlanmamış veya review",
      provisional: false,
    },
  ];
}

export interface FunnelStage {
  key: string;
  label: string;
  value: number;
}

const SUITABLE_STATUSES = new Set(["qualified", "high priority"]);

function suitableCompanyCount(data: DashboardStatsResponse): number {
  if (typeof data.stats.suitable_companies === "number") {
    return data.stats.suitable_companies;
  }
  return data.status_breakdown.reduce(
    (sum, row) => sum + (SUITABLE_STATUSES.has(row.status) ? row.count : 0),
    0,
  );
}

/** Satış akışı — sonraki adımlar (demo/teklif) henüz veri üretmiyorsa 0. */
export function buildFunnelStages(data: DashboardStatsResponse): FunnelStage[] {
  const { stats } = data;

  return [
    { key: "discovery", label: "Keşif", value: stats.analyzed_companies },
    { key: "qualified", label: "Uygun", value: suitableCompanyCount(data) },
    { key: "contact", label: "İletişim", value: stats.total_contacts },
    { key: "demo", label: "Demo", value: 0 },
    { key: "proposal", label: "Teklif", value: 0 },
  ];
}

const EVENT_LABELS: Record<string, string> = {
  company_discovery: "Şirket araştırması",
  website_research: "Web sitesi taraması",
  ai_analysis: "AI analizi",
  decision_maker_search: "Karar verici araması",
  deep_research: "Derin araştırma",
  outreach_prep: "E-posta taslağı",
};

const STATUS_SUFFIX: Record<Activity["status"], string> = {
  success: "tamamlandı",
  running: "sürüyor",
  failed: "başarısız oldu",
  skipped: "atlandı",
};

const EVENT_ICONS: Record<string, LucideIcon> = {
  company_discovery: Building2,
  website_research: Mail,
  ai_analysis: CalendarClock,
  decision_maker_search: MailOpen,
  deep_research: Target,
  outreach_prep: MailOpen,
};

export interface ActivityView {
  title: string;
  description: string;
  tag: string;
  href: string | null;
  icon: LucideIcon;
  tone: "neutral" | "danger";
}

function stringField(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

/** Aktivite kaydındaki siteyi tarayıcıda açılabilir https URL'ye çevirir. */
export function activityWebsiteUrl(activity: Activity): string | null {
  const detail = activity.detail ?? {};
  const candidates = [
    stringField(detail.website),
    stringField(detail.domain),
    stringField(activity.company_name),
  ];

  for (const raw of candidates) {
    if (!raw) continue;
    const href = toHttpUrl(raw);
    if (href) return href;
  }
  return null;
}

function toHttpUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || /\s/.test(trimmed)) return null;
  const withProtocol = /^https?:\/\//i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;
  try {
    const parsed = new URL(withProtocol);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    if (!parsed.hostname.includes(".")) return null;
    return parsed.href;
  } catch {
    return null;
  }
}

function hostnameFromUrl(href: string): string | null {
  try {
    return new URL(href).hostname.replace(/^www\./i, "") || null;
  } catch {
    return null;
  }
}

export function describeActivity(activity: Activity): ActivityView {
  const eventLabel = EVENT_LABELS[activity.event_type] ?? activity.event_type;
  const isFailure = activity.status === "failed";
  const href = activityWebsiteUrl(activity);

  return {
    title: `${eventLabel} ${STATUS_SUFFIX[activity.status]}`,
    description: activity.message,
    tag: (href ? hostnameFromUrl(href) : null) ?? activity.company_name ?? eventLabel,
    href,
    icon: isFailure ? Ban : (EVENT_ICONS[activity.event_type] ?? Sparkles),
    tone: isFailure ? "danger" : "neutral",
  };
}
