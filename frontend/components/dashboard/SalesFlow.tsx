import { Card, CardTitle } from "@/components/ui/Card";
import { formatNumber } from "@/lib/format";
import type { FunnelStage } from "@/lib/metrics";

/** Okun ucu ve sonraki parçanın girinti derinliği (px). */
const POINT = 14;
/** Parçalar arasında görünen ince boşluk (px). */
const SEAM = 2;

export function SalesFlow({ stages }: { stages: FunnelStage[] }) {
  return (
    <Card className="p-4">
      <CardTitle>Satış akışı</CardTitle>

      <ol className="mt-3 flex items-stretch">
        {stages.map((stage, index) => {
          const isFirst = index === 0;

          return (
            <li
              key={stage.key}
              className={`flex-1 py-2.5 ${isFirst ? "bg-brand pl-4" : "bg-line-soft"}`}
              style={{
                clipPath: isFirst
                  ? `polygon(0 0, calc(100% - ${POINT}px) 0, 100% 50%, calc(100% - ${POINT}px) 100%, 0 100%)`
                  : `polygon(0 0, calc(100% - ${POINT}px) 0, 100% 50%, calc(100% - ${POINT}px) 100%, 0 100%, ${POINT}px 50%)`,
                marginLeft: isFirst ? undefined : -(POINT - SEAM),
                paddingLeft: isFirst ? undefined : POINT + 10,
              }}
            >
              <p
                className={`text-[11px] ${isFirst ? "text-on-brand/80" : "text-ink-soft"}`}
              >
                {stage.label}
              </p>
              <p
                className={`tabular text-[20px] leading-tight font-semibold tracking-tight ${
                  isFirst ? "text-on-brand" : "text-ink"
                }`}
              >
                {formatNumber(stage.value)}
              </p>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
