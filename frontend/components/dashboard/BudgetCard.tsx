"use client";

import { useState } from "react";
import { Landmark } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/Card";
import { formatCurrency } from "@/lib/format";

/**
 * Aylık AI operasyon bütçesi.
 *
 * Maliyet takibi backend'de henüz yok; tasarımdaki örnek değerler gösteriliyor.
 */
const SAMPLE_SPENT = 1240;
const SAMPLE_LIMIT = 5000;

interface BudgetCardProps {
  spent?: number;
  limit?: number;
}

export function BudgetCard({
  spent = SAMPLE_SPENT,
  limit = SAMPLE_LIMIT,
}: BudgetCardProps) {
  const [stopAtLimit, setStopAtLimit] = useState(true);

  const ratio = limit > 0 ? Math.min(spent / limit, 1) : 0;
  const percentage = Math.round(ratio * 100);

  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-center gap-1.5">
        <Landmark className="size-3.5 text-ink-soft" strokeWidth={2} />
        <CardTitle>Örnek aylık bütçe</CardTitle>
      </div>

      <div className="mt-3 flex items-end justify-between">
        <p className="tabular text-[22px] leading-none font-semibold tracking-tight text-ink">
          {formatCurrency(spent)}
          <span className="text-[13px] font-medium text-ink-muted">
            {" / "}
            {formatCurrency(limit)}
          </span>
        </p>
        <p className="tabular text-[13px] font-semibold text-ink">
          {percentage}%
        </p>
      </div>

      <div
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Bütçe kullanımı"
        className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-line-soft"
      >
        <div
          className="h-full rounded-full bg-brand-deep"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-ink-muted">
        Bu ayki AI operasyon maliyeti. Belirlediğin limite ulaşıldığında sistem
        otomatik olarak durur.
      </p>

      <label className="mt-auto flex cursor-pointer items-center gap-2 pt-3">
        <span className="relative inline-flex">
          <input
            type="checkbox"
            checked={stopAtLimit}
            onChange={(event) => setStopAtLimit(event.target.checked)}
            className="peer sr-only"
          />
          <span className="block h-4 w-7 rounded-full bg-line transition-colors peer-checked:bg-brand-deep peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40" />
          <span className="absolute top-0.5 left-0.5 size-3 rounded-full bg-white transition-transform peer-checked:translate-x-3" />
        </span>
        <span className="text-[11px] text-ink-soft">Limitte durdur</span>
      </label>
    </Card>
  );
}
