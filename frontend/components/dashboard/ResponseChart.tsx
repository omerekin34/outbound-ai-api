import { Card, CardTitle } from "@/components/ui/Card";

/**
 * "Yanıt ve demo" grafiği.
 *
 * Backend henüz zaman serisi üretmiyor (`outreach_messages` boş), bu yüzden
 * seriler tasarımdaki örnek veriyle çiziliyor. Backend bir
 * `/api/dashboard-timeseries` ucu sunduğunda `series` prop'u oradan beslenebilir.
 */
const SAMPLE_SERIES: Series[] = [
  {
    label: "Olumlu yanıt",
    values: [10, 12, 9, 20, 18, 26, 31],
    lineClass: "stroke-brand",
    dotClass: "fill-brand",
    legendClass: "bg-brand",
  },
  {
    label: "AI demo",
    values: [5, 6, 4, 7, 6, 8, 7],
    lineClass: "stroke-brand-light",
    dotClass: "fill-brand-light",
    legendClass: "bg-brand-light",
  },
];

const SAMPLE_LABELS = [
  "12 Mar",
  "13 Mar",
  "14 Mar",
  "15 Mar",
  "16 Mar",
  "17 Mar",
  "18 Mar",
];

interface Series {
  label: string;
  values: number[];
  lineClass: string;
  dotClass: string;
  legendClass: string;
}

// SVG koordinat sistemi; genişlik `w-full` ile oransal olarak ölçeklenir.
const VIEW_WIDTH = 600;
const VIEW_HEIGHT = 168;
const PLOT_LEFT = 30;
// Son x ekseni etiketinin ortalanınca kırpılmaması için sağda pay bırakılır.
const PLOT_RIGHT = 574;
const PLOT_TOP = 10;
const PLOT_BOTTOM = 132;
const Y_TICKS = [0, 10, 20, 30, 40];
const Y_MAX = 40;

function xFor(index: number, count: number): number {
  if (count <= 1) return PLOT_LEFT;
  return PLOT_LEFT + (index * (PLOT_RIGHT - PLOT_LEFT)) / (count - 1);
}

function yFor(value: number): number {
  const ratio = Math.min(Math.max(value / Y_MAX, 0), 1);
  return PLOT_BOTTOM - ratio * (PLOT_BOTTOM - PLOT_TOP);
}

interface ResponseChartProps {
  series?: Series[];
  labels?: string[];
}

export function ResponseChart({
  series = SAMPLE_SERIES,
  labels = SAMPLE_LABELS,
}: ResponseChartProps) {
  const pointCount = labels.length;

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <CardTitle>Yanıt ve demo</CardTitle>
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

      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="mt-2 h-auto w-full"
        role="img"
        aria-label="Günlük olumlu yanıt ve AI demo sayısı"
      >
        {Y_TICKS.map((tick) => {
          const y = yFor(tick);
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
            .map((value, index) => `${xFor(index, pointCount)},${yFor(value)}`)
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
                  key={index}
                  cx={xFor(index, pointCount)}
                  cy={yFor(value)}
                  r={2.8}
                  className={item.dotClass}
                />
              ))}
            </g>
          );
        })}

        {labels.map((label, index) => (
          <text
            key={label}
            x={xFor(index, pointCount)}
            y={PLOT_BOTTOM + 20}
            textAnchor="middle"
            className="fill-ink-muted text-[9px]"
          >
            {label}
          </text>
        ))}
      </svg>
    </Card>
  );
}
