"use client";

import { Inbox, MailCheck, MailOpen } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/replies/SearchInput";
import { StatTiles } from "@/components/replies/StatTiles";
import {
  ConnectionError,
  EmptyState,
  ReplyTableSkeleton,
  StaleWarning,
} from "@/components/replies/ReplyStates";
import { ReplyTable } from "@/components/replies/ReplyTable";
import { DecisionMakersTable } from "@/components/replies/DecisionMakersTable";
import { markReplyRead, type Reply } from "@/lib/api";
import {
  FILTER_ORDER,
  TONE_CLASSES,
  describeClassification,
} from "@/lib/classification";
import { formatNumber } from "@/lib/format";
import { useDecisionMakers, useInbox } from "@/lib/useReplies";

const PAGE_SIZE = 25;

export function InboxView() {
  const [classification, setClassification] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [search, setSearch] = useState("");

  const contacts = useDecisionMakers({
    limit: PAGE_SIZE,
    offset: 0,
    search: search.trim() || null,
  });
  const { data, error, isLoading, isRefreshing, refresh } = useInbox({
    limit: PAGE_SIZE,
    offset: 0,
    classification,
    unreadOnly,
    search: search.trim() || null,
  });

  async function handleToggleRead(reply: Reply) {
    try {
      await markReplyRead(reply.id, !reply.is_read);
    } finally {
      // Sunucu son durumu döndürse de sayaçlar için listeyi yeniliyoruz.
      refresh();
    }
  }

  const counts = new Map(
    (data?.classification_breakdown ?? []).map((row) => [
      row.classification,
      row.count,
    ]),
  );
  const hasFilter = classification !== null || unreadOnly || search.trim() !== "";

  return (
    <div className="space-y-5">
      <PageHeader
        title="Gelen Kutusu"
        subtitle="AI'ın sınıflandırdığı gelen e-posta yanıtları."
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

      {isLoading ? <ReplyTableSkeleton /> : null}

      {!isLoading && error && !data ? (
        <ConnectionError message={error} onRetry={refresh} endpoint="/api/inbox" />
      ) : null}

      {data ? (
        <>
          <StatTiles
            tiles={[
              {
                key: "total",
                label: "Gelen yanıt",
                value: formatNumber(data.inbound_total),
                icon: Inbox,
                caption: "Sınıflandırılmış tüm yanıtlar",
              },
              {
                key: "unread",
                label: "Okunmamış",
                value: formatNumber(data.unread_count),
                icon: MailOpen,
                tone: "accent",
                caption: "Henüz incelenmedi",
              },
              {
                key: "positive",
                label: "Olumlu yanıt",
                value: formatNumber(data.positive_count),
                icon: MailCheck,
                caption: "Fırsatlar ekranında listelenir",
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

          <Card className="p-4">
            <div className="flex flex-wrap items-center gap-1.5 pb-3">
              <FilterChip
                label="Tümü"
                count={data.inbound_total}
                isActive={classification === null && !unreadOnly}
                onClick={() => {
                  setClassification(null);
                  setUnreadOnly(false);
                }}
              />
              <FilterChip
                label="Okunmamış"
                count={data.unread_count}
                isActive={unreadOnly}
                onClick={() => {
                  setUnreadOnly(!unreadOnly);
                  setClassification(null);
                }}
              />

              <span className="mx-1 h-4 w-px bg-line" aria-hidden />

              {FILTER_ORDER.filter((key) => counts.has(key)).map((key) => {
                const view = describeClassification(key);
                return (
                  <FilterChip
                    key={key}
                    label={view.label}
                    count={counts.get(key) ?? 0}
                    tone={TONE_CLASSES[view.tone]}
                    isActive={classification === key}
                    onClick={() => {
                      setClassification(classification === key ? null : key);
                      setUnreadOnly(false);
                    }}
                  />
                );
              })}
            </div>

            {data.items.length === 0 ? (
              <div className="py-6">
                {hasFilter ? (
                  <p className="text-center text-[12px] text-ink-soft">
                    Bu filtreye uyan yanıt yok.
                  </p>
                ) : (
                  <p className="text-center text-[12px] text-ink-soft">
                    Henüz gelen yanıt yok.
                  </p>
                )}
              </div>
            ) : (
              <ReplyTable items={data.items} onToggleRead={handleToggleRead} />
            )}
          </Card>

          {data.total === 0 && !hasFilter ? (
            <EmptyState
              icon={Inbox}
              title="Gelen kutusu boş"
              description="Kampanya yanıtları geldikçe AI bunları sınıflandırıp burada listeleyecek. Karar vericiler Apollo’dan nitelikli şirketlere bağlanır; sahte kişi eklenmez."
            />
          ) : null}

          {data.total > data.items.length ? (
            <p className="text-right text-[11px] text-ink-muted">
              {formatNumber(data.items.length)} / {formatNumber(data.total)} yanıt
              gösteriliyor
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function FilterChip({
  label,
  count,
  isActive,
  tone,
  onClick,
}: {
  label: string;
  count: number;
  isActive: boolean;
  tone?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        isActive
          ? "border-ink bg-ink text-white"
          : (tone ?? "border-line bg-surface text-ink-soft hover:border-brand hover:text-brand")
      }`}
    >
      {label}
      <span className={`tabular ${isActive ? "text-white/70" : "opacity-60"}`}>
        {formatNumber(count)}
      </span>
    </button>
  );
}
