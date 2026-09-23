import { Landmark } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/Card";

/** Bütçe backend'e bağlı değil; örnek tutar gösterilmez. */
export function BudgetCard() {
  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-center gap-1.5">
        <Landmark className="size-3.5 text-ink-soft" strokeWidth={2} />
        <CardTitle>Aylık bütçe</CardTitle>
      </div>
      <p className="mt-3 text-[22px] font-semibold tracking-tight text-ink">—</p>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
        AI operasyon maliyeti henüz Neon’dan okunmuyor. Sahte tutar yok.
      </p>
    </Card>
  );
}
