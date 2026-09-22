import { ArrowUpRight, Triangle } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { formatNumber } from "@/lib/format";
import type { MetricCard } from "@/lib/metrics";

export function MetricCards({ cards }: { cards: MetricCard[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <MetricCardTile key={card.key} card={card} />
      ))}
    </div>
  );
}

function MetricCardTile({ card }: { card: MetricCard }) {
  const Icon = card.icon;

  const body = (
    <>
      <div className="flex items-center gap-2">
        <span
          className={`flex size-7 items-center justify-center rounded-lg ${
            card.tone === "accent"
              ? "bg-accent-soft text-accent"
              : "bg-brand-soft text-brand"
          }`}
        >
          <Icon className="size-3.5" strokeWidth={2} />
        </span>
        <p
          className="truncate text-[12px] text-ink-soft"
          title={
            card.provisional
              ? `${card.label} için backend'de birebir kaynak yok — geçici olarak "${card.caption}" alanına bağlı.`
              : undefined
          }
        >
          {card.label}
        </p>

        {card.href ? (
          <ArrowUpRight
            className="ml-auto size-3.5 shrink-0 text-ink-muted transition-colors group-hover:text-brand"
            strokeWidth={2}
          />
        ) : null}
      </div>

      <p className="tabular mt-2.5 text-[28px] leading-none font-semibold tracking-tight text-ink">
        {formatNumber(card.value)}
      </p>

      <div className="mt-2 flex h-4 items-center gap-1">
        {card.delta !== null && card.delta > 0 ? (
          <>
            <Triangle className="size-2 fill-brand text-brand" />
            <span className="text-[11px] font-semibold text-brand">
              +{formatNumber(card.delta)}
            </span>
          </>
        ) : null}
      </div>

      <p
        className={`text-[11px] ${
          card.href
            ? "text-ink-muted transition-colors group-hover:text-brand"
            : "text-ink-muted"
        }`}
      >
        {card.caption}
      </p>
    </>
  );

  if (!card.href) {
    return <Card className="p-4">{body}</Card>;
  }

  return (
    <Link
      href={card.href}
      aria-label={`${card.label}: ${formatNumber(card.value)} — ${card.caption}`}
      className="group rounded-card focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
    >
      <Card className="h-full p-4 transition-colors hover:border-brand">
        {body}
      </Card>
    </Link>
  );
}
