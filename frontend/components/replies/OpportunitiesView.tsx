"use client";

import { Building2, Gauge, Target } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/replies/SearchInput";
import { StatTiles } from "@/components/replies/StatTiles";
import { DecisionMakersTable } from "@/components/replies/DecisionMakersTable";
import {
  ConnectionError,
  EmptyState,
  ReplyTableSkeleton,
  StaleWarning,
} from "@/components/replies/ReplyStates";
import { ReplyTable } from "@/components/replies/ReplyTable";
import { formatNumber } from "@/lib/format";
import { useDecisionMakers, useOpportunities } from "@/lib/useReplies";

const PAGE_SIZE = 25;

export function OpportunitiesView() {
  const [search, setSearch] = useState("");

  const { data, error, isLoading, isRefreshing, refresh } = useOpportunities({
    limit: PAGE_SIZE,
    offset: 0,
    search: search.trim() || null,
  });
  const contacts = useDecisionMakers({
    limit: PAGE_SIZE,
    offset: 0,
    search: search.trim() || null,
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Fırsatlar"
        subtitle="Apollo’dan bulunan karar vericiler ve olumlu yanıtlar. Sahte isim yok."
        isRefreshing={isRefreshing || contacts.isRefreshing}
        onRefresh={() => {
          refresh();
          contacts.refresh();
        }}
      >
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Şirket, kişi veya metin ara"
        />
      </PageHeader>

      {error && data ? <StaleWarning message={error} /> : null}

      {isLoading ? <ReplyTableSkeleton rows={4} /> : null}

      {!isLoading && error && !data ? (
        <ConnectionError
          message={error}
          onRetry={refresh}
          endpoint="/api/opportunities"
        />
      ) : null}

      {data ? (
        <>
          <StatTiles
            tiles={[
              {
                key: "total",
                label: "Açık fırsat",
                value: formatNumber(data.total),
                icon: Target,
                caption: "Olumlu ve toplantı talebi yanıtları",
              },
              {
                key: "decision-makers",
                label: "Karar verici",
                value: formatNumber(contacts.data?.total ?? 0),
                icon: Building2,
                caption: "Apollo’dan kaydedilen kişiler",
              },
              {
                key: "score",
                label: "Ortalama puan",
                value:
                  data.average_score === null
                    ? "—"
                    : data.average_score.toLocaleString("tr-TR", {
                        maximumFractionDigits: 1,
                      }),
                icon: Gauge,
                tone: "accent",
                caption: "Şirket başına genel puan",
              },
            ]}
          />

          <div className="space-y-2">
            <h2 className="text-[13px] font-semibold text-ink">Karar vericiler</h2>
            {contacts.isLoading ? (
              <ReplyTableSkeleton rows={3} />
            ) : contacts.error && !contacts.data ? (
              <ConnectionError
                message={contacts.error}
                onRetry={contacts.refresh}
                endpoint="/api/contacts"
              />
            ) : (
              <DecisionMakersTable items={contacts.data?.items ?? []} />
            )}
          </div>

          <h2 className="text-[13px] font-semibold text-ink">Olumlu yanıtlar</h2>
          {data.items.length === 0 ? (
            search.trim() ? (
              <Card className="p-8">
                <p className="text-center text-[12px] text-ink-soft">
                  “{search.trim()}” için fırsat bulunamadı.
                </p>
              </Card>
            ) : (
              <EmptyState
                icon={Target}
                title="Henüz fırsat yok"
                description="AI bir yanıtı “Olumlu” veya “Toplantı talebi” olarak sınıflandırdığında fırsat otomatik olarak burada görünür. Gelen kutusunda bekleyen yanıtları inceleyebilirsiniz."
              />
            )
          ) : (
            <Card className="p-4">
              <ReplyTable items={data.items} showScore />
            </Card>
          )}

          <p className="flex items-center justify-between pt-1 text-[11px] text-ink-muted">
            <Link
              href="/inbox"
              className="transition-colors hover:text-brand hover:underline"
            >
              Tüm yanıtlar için Gelen Kutusu →
            </Link>
            {data.total > data.items.length ? (
              <span>
                {formatNumber(data.items.length)} / {formatNumber(data.total)} fırsat
                gösteriliyor
              </span>
            ) : null}
          </p>
        </>
      ) : null}
    </div>
  );
}
