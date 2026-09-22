import {
  TONE_CLASSES,
  describeClassification,
  formatConfidence,
} from "@/lib/classification";

interface ClassificationBadgeProps {
  classification: string | null;
  confidence?: number | null;
  /** Güven oranını rozetin yanında göster. */
  showConfidence?: boolean;
}

/** AI sınıflandırma etiketi — "Olumlu" yeşil, "Olumsuz" kırmızı. */
export function ClassificationBadge({
  classification,
  confidence = null,
  showConfidence = false,
}: ClassificationBadgeProps) {
  const view = describeClassification(classification);
  const Icon = view.icon;
  const confidenceLabel = showConfidence ? formatConfidence(confidence) : null;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${TONE_CLASSES[view.tone]}`}
      >
        <Icon className="size-3" strokeWidth={2.2} />
        {view.label}
      </span>
      {confidenceLabel ? (
        <span className="tabular text-[11px] text-ink-muted">
          {confidenceLabel}
        </span>
      ) : null}
    </span>
  );
}
