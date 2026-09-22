import { ArrowRight, TriangleAlert } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/Card";

export interface Decision {
  id: string;
  title: string;
  detail: string;
}

/**
 * Onay bekleyen kararlar.
 *
 * Backend'de karar kuyruğu tablosu henüz yok; tasarımdaki örnek kayıtlar
 * gösteriliyor. Kuyruk eklendiğinde `decisions` prop'u API'den beslenmeli.
 */
const SAMPLE_DECISIONS: Decision[] = [
  {
    id: "discount-limit",
    title: "İndirim sınırı aşıldı",
    detail: "Örnek teklif • %12 talep",
  },
  {
    id: "contract-term",
    title: "Yeni sözleşme koşulu",
    detail: "Veri konumu taahhüdü",
  },
];

export function DecisionList({
  decisions = SAMPLE_DECISIONS,
}: {
  decisions?: Decision[];
}) {
  return (
    <Card className="p-4">
      <CardTitle>Sana gereken {decisions.length} karar</CardTitle>

      <ul className="mt-3 space-y-2">
        {decisions.map((decision) => (
          <li key={decision.id}>
            <button
              type="button"
              className="flex w-full items-center gap-2.5 rounded-xl border border-accent-line bg-accent-soft px-3 py-2.5 text-left transition-colors hover:border-accent/40"
            >
              <TriangleAlert
                className="size-4 shrink-0 text-accent"
                strokeWidth={2}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-semibold text-ink">
                  {decision.title}
                </span>
                <span className="block truncate text-[11px] text-ink-soft">
                  {decision.detail}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-accent">
                İncele
                <ArrowRight className="size-3" />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
