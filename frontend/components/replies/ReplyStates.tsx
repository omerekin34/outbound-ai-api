import { TriangleAlert, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { API_BASE_URL } from "@/lib/api";

export function ReplyTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Card className="p-4">
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-3">
            <div className="h-9 w-[22%] animate-pulse rounded-lg bg-line-soft" />
            <div className="h-9 w-[22%] animate-pulse rounded-lg bg-line-soft" />
            <div className="h-9 flex-1 animate-pulse rounded-lg bg-line-soft" />
            <div className="h-6 w-24 animate-pulse rounded-full bg-line-soft" />
          </div>
        ))}
      </div>
    </Card>
  );
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  hint?: string;
}

export function EmptyState({ icon: Icon, title, description, hint }: EmptyStateProps) {
  return (
    <Card className="p-10">
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 text-center">
        <span className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
          <Icon className="size-5" strokeWidth={1.9} />
        </span>
        <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
        <p className="text-[12px] leading-relaxed text-ink-soft">{description}</p>
        {hint ? (
          <code className="rounded-lg bg-line-soft px-2 py-1 text-[11px] text-ink-soft">
            {hint}
          </code>
        ) : null}
      </div>
    </Card>
  );
}

export function ConnectionError({
  message,
  onRetry,
  endpoint,
}: {
  message: string;
  onRetry: () => void;
  endpoint: string;
}) {
  return (
    <Card className="p-8">
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 text-center">
        <span className="flex size-9 items-center justify-center rounded-xl bg-danger-soft text-danger">
          <TriangleAlert className="size-4" strokeWidth={2} />
        </span>
        <h2 className="text-[14px] font-semibold text-ink">Veriler yüklenemedi</h2>
        <p className="text-[12px] leading-relaxed text-ink-soft">{message}</p>
        <p className="text-[11px] text-ink-muted">
          Beklenen adres: {API_BASE_URL}
          {endpoint}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-lg bg-ink px-3.5 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-brand-deep"
        >
          Tekrar dene
        </button>
      </div>
    </Card>
  );
}

/** Veri varken oluşan yenileme hatası için ince uyarı şeridi. */
export function StaleWarning({ message }: { message: string }) {
  return (
    <p className="flex items-center gap-2 rounded-xl border border-accent-line bg-accent-soft px-3 py-2 text-[11px] text-accent">
      <TriangleAlert className="size-3.5 shrink-0" />
      Liste yenilenemedi, en son alınan veriler gösteriliyor. {message}
    </p>
  );
}
