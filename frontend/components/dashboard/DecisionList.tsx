import { ArrowRight, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/Card";
import type { CompanyRow } from "@/lib/api";

export function DecisionList({ companies }: { companies: CompanyRow[] }) {
  return (
    <Card className="p-4">
      <CardTitle>
        {companies.length === 0
          ? "Onay bekleyen karar yok"
          : `Sana gereken ${companies.length} karar`}
      </CardTitle>

      {companies.length === 0 ? (
        <p className="mt-3 text-[12px] leading-relaxed text-ink-soft">
          İnceleme bekleyen şirketler burada listelenir. Sahte karar kaydı
          yok.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {companies.map((company) => (
            <li key={company.id}>
              <Link
                href="/sirketler"
                className="flex w-full items-center gap-2.5 rounded-xl border border-accent-line bg-accent-soft px-3 py-2.5 text-left transition-colors hover:border-accent/40"
              >
                <TriangleAlert
                  className="size-4 shrink-0 text-accent"
                  strokeWidth={2}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-semibold text-ink">
                    {company.name ?? company.domain ?? "Şirket"}
                  </span>
                  <span className="block truncate text-[11px] text-ink-soft">
                    {company.qualification_status ?? company.status ?? "review"}
                    {company.overall_score != null
                      ? ` · genel ${company.overall_score}`
                      : ""}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-accent">
                  İncele
                  <ArrowRight className="size-3" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
