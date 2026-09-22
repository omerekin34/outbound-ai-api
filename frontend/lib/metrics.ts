import {
  Ban,
  Building2,
  CalendarClock,
  Cpu,
  Hourglass,
  Mail,
  MailOpen,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import type { Activity, DashboardStatsResponse } from "./api";

/**
 * Tasarımdaki kartların hangi backend alanından beslendiği burada tanımlanır.
 *
 * `provisional: true` olan kartların backend'de birebir karşılığı YOK; en yakın
 * gerçek alana bağlandılar. Demo planlaması veri üretmeye başladığında
 * "AI demo" kartı planlanan demo sayısına taşınmalı.
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
  /** Doluysa kart tıklanabilir olur ve bu adrese gider. */
  href?: string;
}

export function buildMetricCards(data: DashboardStatsResponse): MetricCard[] {
  const { stats } = data;

  return [
    {
      key: "researched",
      label: "Araştırılan şirket",
      value: stats.total_companies,
      icon: Building2,
      tone: "brand",
      delta: stats.companies_added_last_7_days,
      caption: "Son 7 günde eklenen",
      provisional: false,
    },
    {
      key: "positive-reply",
      label: "Olumlu yanıt",
      value: stats.positive_replies,
      icon: MailOpen,
      tone: "brand",
      delta: null,
      caption: "Fırsatlar ekranını aç",
      provisional: false,
      href: "/opportunities",
    },
    {
      key: "ai-demo",
      label: "AI demo",
      value: stats.analyzed_companies,
      icon: Cpu,
      tone: "brand",
      delta: null,
      caption: "AI analizi tamamlanan",
      provisional: true,
    },
    {
      key: "awaiting-decision",
      label: "Karar bekleyen",
      value: stats.pending_companies,
      icon: Hourglass,
      tone: "accent",
      delta: null,
      caption: "Araştırma sırasında bekliyor",
      provisional: false,
    },
  ];
}

export interface FunnelStage {
  key: string;
  label: string;
  value: number;
}

/** "Satış akışı" hunisi — her adım gerçek bir backend sayacına bağlı. */
export function buildFunnelStages(data: DashboardStatsResponse): FunnelStage[] {
  const { stats } = data;

  return [
    { key: "discovery", label: "Keşif", value: stats.total_companies },
    { key: "qualified", label: "Uygun", value: stats.researched_companies },
    { key: "contact", label: "İletişim", value: stats.total_contacts },
    { key: "demo", label: "Demo", value: stats.analyzed_companies },
    { key: "proposal", label: "Teklif", value: stats.high_intent_companies },
  ];
}

const EVENT_LABELS: Record<string, string> = {
  company_discovery: "Şirket araştırması",
  website_research: "Web sitesi taraması",
  ai_analysis: "AI analizi",
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
};

export interface ActivityView {
  title: string;
  description: string;
  tag: string;
  icon: LucideIcon;
  tone: "neutral" | "danger";
}

export function describeActivity(activity: Activity): ActivityView {
  const eventLabel = EVENT_LABELS[activity.event_type] ?? activity.event_type;
  const isFailure = activity.status === "failed";

  return {
    title: `${eventLabel} ${STATUS_SUFFIX[activity.status]}`,
    description: activity.message,
    tag: activity.company_name ?? eventLabel,
    icon: isFailure ? Ban : (EVENT_ICONS[activity.event_type] ?? Sparkles),
    tone: isFailure ? "danger" : "neutral",
  };
}
