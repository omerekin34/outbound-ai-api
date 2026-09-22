import {
  BellOff,
  CalendarCheck,
  CircleHelp,
  CircleMinus,
  MailCheck,
  MailX,
  Moon,
  type LucideIcon,
} from "lucide-react";

/**
 * AI sınıflandırmalarının ekran karşılıkları.
 *
 * Anahtarlar `api/models.py` içindeki `Interaction.CLASS_*` sabitleriyle
 * birebir aynıdır. Backend'e yeni bir sınıf eklenirse buraya da eklenmeli;
 * eklenmezse `describeClassification` güvenli bir varsayılana düşer.
 */
export type ClassificationTone = "positive" | "warning" | "neutral" | "danger";

export interface ClassificationView {
  label: string;
  tone: ClassificationTone;
  icon: LucideIcon;
}

const VIEWS: Record<string, ClassificationView> = {
  positive: { label: "Olumlu", tone: "positive", icon: MailCheck },
  meeting_request: {
    label: "Toplantı talebi",
    tone: "positive",
    icon: CalendarCheck,
  },
  question: { label: "Soru", tone: "warning", icon: CircleHelp },
  neutral: { label: "Nötr", tone: "neutral", icon: CircleMinus },
  negative: { label: "Olumsuz", tone: "danger", icon: MailX },
  unsubscribe: { label: "Listeden çıkma", tone: "danger", icon: BellOff },
  auto_reply: { label: "Otomatik yanıt", tone: "neutral", icon: Moon },
};

const UNCLASSIFIED: ClassificationView = {
  label: "Sınıflandırılmadı",
  tone: "neutral",
  icon: CircleMinus,
};

export function describeClassification(
  classification: string | null | undefined,
): ClassificationView {
  if (!classification || classification === "unclassified") {
    return UNCLASSIFIED;
  }
  return VIEWS[classification] ?? { ...UNCLASSIFIED, label: classification };
}

/** Rozet ve çip renkleri — palet `app/globals.css` içinde tanımlı. */
export const TONE_CLASSES: Record<ClassificationTone, string> = {
  positive: "border-brand-soft bg-brand-soft text-brand",
  warning: "border-accent-line bg-accent-soft text-accent",
  neutral: "border-line bg-line-soft text-ink-soft",
  danger: "border-danger-soft bg-danger-soft text-danger",
};

/** Gelen kutusu filtre çiplerinin sırası: en eyleme dönük olan başta. */
export const FILTER_ORDER = [
  "positive",
  "meeting_request",
  "question",
  "neutral",
  "negative",
  "auto_reply",
  "unsubscribe",
] as const;

/** Güven oranını "%93" biçiminde gösterir. */
export function formatConfidence(confidence: number | null): string | null {
  if (confidence === null || Number.isNaN(confidence)) {
    return null;
  }
  return `%${Math.round(confidence * 100)}`;
}
