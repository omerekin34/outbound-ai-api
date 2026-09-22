"use client";

import { MailCheck, RefreshCw, Search } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError, startResearch } from "@/lib/api";

export function DiscoveryView() {
  const [domain, setDomain] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = domain.trim();
    if (!value || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setToast(null);
    try {
      const accepted = await startResearch(value);
      setToast(accepted.message || "Research started in the background");
      setDomain("");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Araştırma başlatılamadı.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Keşif"
        subtitle="Bir alan adı girin; tarama, fact çıkarımı, puanlama ve Apollo araması arka planda çalışır."
      />

      <Card className="mx-auto max-w-xl p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium text-ink">Şirket domain’i</span>
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted"
                strokeWidth={2}
              />
              <input
                type="text"
                name="domain"
                value={domain}
                onChange={(event) => setDomain(event.target.value)}
                placeholder="ornekmakina.com.tr"
                autoComplete="off"
                spellCheck={false}
                disabled={isSubmitting}
                className="w-full rounded-xl border border-line bg-canvas py-2.5 pr-3 pl-10 text-[13px] text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none disabled:opacity-60"
              />
            </div>
          </label>

          <button
            type="submit"
            disabled={isSubmitting || domain.trim() === ""}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? (
              <RefreshCw className="size-4 animate-spin" strokeWidth={2} />
            ) : (
              <Search className="size-4" strokeWidth={2} />
            )}
            Start Research
          </button>
        </form>

        {toast ? (
          <p
            role="status"
            className="mt-4 flex items-center gap-2 rounded-xl border border-brand/20 bg-brand-soft px-3 py-2 text-[12px] text-brand"
          >
            <MailCheck className="size-3.5 shrink-0" strokeWidth={2} />
            {toast}
          </p>
        ) : null}

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-xl border border-danger/20 bg-danger-soft px-3 py-2 text-[12px] text-danger"
          >
            {error}
          </p>
        ) : null}
      </Card>
    </div>
  );
}
