import { ChevronRight, Inbox } from "lucide-react";

import { Card, CardTitle } from "@/components/ui/Card";
import type { AiState, AiStatus } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/format";
import { describeActivity } from "@/lib/metrics";

const STATE_STYLES: Record<AiState, { label: string; className: string }> = {
  working: { label: "Çalışıyor", className: "bg-brand-soft text-brand-deep" },
  idle: { label: "Beklemede", className: "bg-line-soft text-ink-soft" },
  stalled: { label: "Takıldı", className: "bg-accent-soft text-accent" },
  error: { label: "Hata", className: "bg-danger-soft text-danger" },
};

export function ActivityFeed({ aiStatus }: { aiStatus: AiStatus }) {
  const state = STATE_STYLES[aiStatus.state];

  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-center justify-between gap-3">
        <CardTitle>AI şu anda ne yapıyor?</CardTitle>
        <span
          className={`flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${state.className}`}
        >
          {aiStatus.state === "working" ? (
            <span className="size-1.5 animate-pulse rounded-full bg-brand" />
          ) : null}
          {state.label}
        </span>
      </div>

      <p className="mt-1 text-[11px] text-ink-muted">{aiStatus.headline}</p>

      {aiStatus.recent.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-10 text-center">
          <Inbox className="size-5 text-ink-muted" strokeWidth={1.8} />
          <p className="text-[12px] text-ink-soft">Henüz işlem kaydı yok.</p>
          <p className="max-w-[280px] text-[11px] text-ink-muted">
            Bir şirket keşfi veya web sitesi taraması başlattığınızda adımlar
            burada canlı olarak listelenir.
          </p>
        </div>
      ) : (
        <ul className="mt-3 divide-y divide-line-soft">
          {aiStatus.recent.map((activity) => {
            const view = describeActivity(activity);
            const Icon = view.icon;
            const duration = formatDuration(activity.duration_ms);

            return (
              <li key={activity.id}>
                <div className="group flex w-full items-center gap-3 py-2.5 text-left">
                  <span
                    className={`flex size-6 shrink-0 items-center justify-center rounded-lg ${
                      view.tone === "danger"
                        ? "bg-danger-soft text-danger"
                        : "bg-line-soft text-ink-soft"
                    }`}
                  >
                    <Icon className="size-3.5" strokeWidth={2} />
                  </span>

                  <time
                    dateTime={activity.created_at}
                    className="tabular w-9 shrink-0 text-[11px] text-ink-muted"
                  >
                    {formatTime(activity.created_at)}
                  </time>

                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12px] font-semibold text-ink">
                      {view.title}
                    </span>
                    <span className="block truncate text-[11px] text-ink-soft">
                      {view.description}
                    </span>
                  </span>

                  {duration ? (
                    <span className="tabular hidden shrink-0 text-[10px] text-ink-muted lg:block">
                      {duration}
                    </span>
                  ) : null}

                  {view.href ? (
                    <a
                      href={view.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`${view.tag} sitesini aç`}
                      className="flex max-w-[140px] shrink-0 items-center gap-1 text-[11px] text-ink-muted transition-colors hover:text-brand"
                    >
                      <span className="hidden truncate sm:block">{view.tag}</span>
                      <ChevronRight className="size-3.5 shrink-0 transition-transform group-hover:translate-x-0.5" />
                    </a>
                  ) : (
                    <>
                      <span className="hidden max-w-[110px] shrink-0 truncate text-[11px] text-ink-muted sm:block">
                        {view.tag}
                      </span>
                      <ChevronRight className="size-3.5 shrink-0 text-ink-muted" />
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
