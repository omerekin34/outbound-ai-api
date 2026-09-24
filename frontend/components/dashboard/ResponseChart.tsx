import { Card, CardTitle } from "@/components/ui/Card";
import type { DailyCount } from "@/lib/api";

interface Series {
  label: string;
  values: number[];
  lineClass: string;
  dotClass: string;
  legendClass: string;
}

const VIEW_WIDTH = 600;
const VIEW_HEIGHT = 168;
const PLOT_LEFT = 30;
const PLOT_RIGHT = 574;
const PLOT_TOP = 10;
const PLOT_BOTTOM = 132;

function xFor(index: number, count: number): number {
  if (count <= 1) return PLOT_LEFT;
  return PLOT_LEFT + (index * (PLOT_RIGHT - PLOT_LEFT)) / (count - 1);
}

function yFor(value: number, yMax: number): number {
  const ratio = yMax <= 0 ? 0 : Math.min(Math.max(value / yMax, 0), 1);
  return PLOT_BOTTOM - ratio * (PLOT_BOTTOM - PLOT_TOP);
}

export function ResponseChart({
  daily,
  title = "Son 7 gün",
}: {
  daily: DailyCount[];
  title?: string;
}) {
  const labels = daily.map((row) => row.label);
  const series: Series[] = [
    {
      label: "Olumlu yanıt",
      values: daily.map((row) => row.positive_replies),
      lineClass: "stroke-success",
      dotClass: "fill-success",
      legendClass: "bg-success",
    },
    {
      label: "Analiz edilen",
      values: daily.map((row) => row.analyzed),
      lineClass: "stroke-brand",
      dotClass: "fill-brand",
      legendClass: "bg-brand",
    },
  ];
  const peak = Math.max(0, ...series.flatMap((item) => item.values));
  const yMax = peak <= 4 ? 4 : Math.ceil(peak / 2) * 2;
  const yTicks = [0, yMax / 2, yMax];
  const pointCount = labels.length;
  const labelStep = pointCount > 14 ? 4 : pointCount > 8 ? 2 : 1;

  return (
    <Card className="p-4" id="gunluk-ozet">
      <div className="flex items-start justify-between">
        <CardTitle>{title}</CardTitle>
        <ul className="flex items-center gap-3">
          {series.map((item) => (
            <li
              key={item.label}
              className="flex items-center gap-1.5 text-[11px] text-ink-soft"
            >
              <span className={`size-1.5 rounded-full ${item.legendClass}`} />
              {item.label}
            </li>
          ))}
        </ul>
      </div>

      {pointCount === 0 ? (
        <p className="py-10 text-center text-[12px] text-ink-soft">
          Henüz günlük veri yok.
        </p>
      ) : (
        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
          className="mt-2 h-auto w-full"
          role="img"
          aria-label={`${title}: analiz edilen şirket ve olumlu yanıt`}
        >
          {yTicks.map((tick) => {
            const y = yFor(tick, yMax);
            return (
              <g key={tick}>
                <line
                  x1={PLOT_LEFT}
                  x2={PLOT_RIGHT}
                  y1={y}
                  y2={y}
                  className="stroke-line-soft"
                  strokeWidth={1}
                />
                <text
                  x={PLOT_LEFT - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-ink-muted text-[9px]"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {series.map((item) => {
            const points = item.values
              .map((value, index) => `${xFor(index, pointCount)},${yFor(value, yMax)}`)
              .join(" ");

            return (
              <g key={item.label}>
                <polyline
                  points={points}
                  fill="none"
                  className={item.lineClass}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {item.values.map((value, index) => (
                  <circle
                    key={`${item.label}-${index}`}
                    cx={xFor(index, pointCount)}
                    cy={yFor(value, yMax)}
                    r={2.8}
                    className={item.dotClass}
                  />
                ))}
              </g>
            );
          })}

          {labels.map((label, index) => (
            <text
              key={`${label}-${index}`}
              x={xFor(index, pointCount)}
              y={PLOT_BOTTOM + 20}
              textAnchor="middle"
              className="fill-ink-muted text-[9px]"
            >
              {index % labelStep === 0 || index === pointCount - 1 ? label : ""}
            </text>
          ))}
        </svg>
      )}
    </Card>
  );
}
