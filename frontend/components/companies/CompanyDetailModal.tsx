"use client";

import { Mail, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  EmailStatusBadge,
  isUsableEmailStatus,
} from "@/components/companies/EmailStatusBadge";
import { ApiError, saveContactEmail, type CompanyContact, type CompanyRow } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  new: "Yeni",
  pending: "Bekliyor",
  qualified: "Nitelikli",
  "high priority": "Yüksek öncelik",
  "low priority": "Düşük öncelik",
  reject: "Red",
  review: "İnceleme",
  timeout: "Zaman aşımı",
  failed: "Başarısız",
};

function scoreLabel(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
}

export function CompanyDetailModal({
  company,
  onClose,
  onContactSaved,
}: {
  company: CompanyRow;
  onClose: () => void;
  onContactSaved?: (contact: CompanyContact) => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const status = company.qualification_status ?? company.status ?? "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 px-4 py-10"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="company-detail-title"
        className="w-full max-w-2xl rounded-card border border-line bg-surface p-5 shadow-[0_16px_40px_rgba(22,36,31,0.16)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">
              Şirket detayı
            </p>
            <h2
              id="company-detail-title"
              className="mt-1 truncate text-[18px] font-semibold tracking-tight text-ink"
            >
              {company.name ?? company.domain ?? "İsimsiz şirket"}
            </h2>
            <p className="mt-0.5 text-[12px] text-ink-soft">
              {company.domain ?? "—"}
              {status ? ` · ${STATUS_LABEL[status] ?? status}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-line text-ink-soft hover:text-ink"
            aria-label="Kapat"
          >
            <X className="size-3.5" strokeWidth={2} />
          </button>
        </div>

        <dl className="mt-4 grid grid-cols-3 gap-2">
          <ScoreTile label="ICP" value={scoreLabel(company.icp_score)} />
          <ScoreTile label="Need" value={scoreLabel(company.need_score)} />
          <ScoreTile label="Genel" value={scoreLabel(company.overall_score)} />
        </dl>

        <section className="mt-4 rounded-xl border border-brand-soft bg-brand-soft/40 p-3.5">
          <p className="text-[11px] font-medium tracking-wide text-brand uppercase">
            ERP kanıtı
          </p>
          <p className="mt-1 text-[14px] font-semibold text-ink">
            {company.erp_signal && company.erp_signal !== "unknown"
              ? company.erp_signal
              : "unknown"}
          </p>
          <p className="mt-1 text-[11px] text-ink-soft">
            güven {company.erp_confidence == null ? "—" : company.erp_confidence.toFixed(2)}
            {" · "}
            kanıt {company.erp_evidence_count ?? 0}
          </p>
          <p className="mt-3 text-[11px] font-medium tracking-wide text-brand uppercase">
            Ağrı hipotezi
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink">
            {company.pain_hypothesis ??
              "Nitelikli şirketlerde derin araştırma sonrası yazılır."}
          </p>
        </section>

        {company.outreach_strategy ? (
          <section className="mt-4 rounded-xl border border-line px-3.5 py-3">
            <p className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">
              Mesaj stratejisi
            </p>
            <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {(
                [
                  ["Ana ağrı", company.outreach_strategy.main_pain],
                  ["Ürün", company.outreach_strategy.recommended_product],
                  ["Satış açısı", company.outreach_strategy.best_sales_angle],
                  ["Persona", company.outreach_strategy.best_persona],
                  ["Neden şimdi", company.outreach_strategy.why_now],
                ] as const
              ).map(([label, value]) => (
                <div key={label}>
                  <dt className="text-[11px] text-ink-muted">{label}</dt>
                  <dd className="text-[12px] text-ink">{value ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        <section className="mt-4">
          <h3 className="text-[12px] font-semibold text-ink">Kanıtlar</h3>
          {company.facts.length === 0 ? (
            <p className="mt-2 text-[12px] text-ink-muted">Kanıt henüz yok.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {company.facts.map((fact) => (
                <li
                  key={`${company.id}-${fact.fact_type}-${fact.value}`}
                  className="rounded-lg border border-line-soft px-3 py-2"
                >
                  <p className="text-[11px] text-ink-muted">{fact.fact_type}</p>
                  <p className="text-[13px] text-ink">{fact.value}</p>
                  <p className="mt-0.5 text-[12px] text-ink-soft">
                    {fact.evidence_text}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mt-4">
          <h3 className="text-[12px] font-semibold text-ink">
            Karar vericiler ve soğuk e-posta
          </h3>
          {company.contacts.length === 0 ? (
            <p className="mt-2 text-[12px] text-ink-muted">
              Apollo kişisi yok. Doğrulama ve taslak yalnızca nitelikli şirket
              kişileri için üretilir.
            </p>
          ) : (
            <ul className="mt-2 space-y-3">
              {company.contacts.map((person) => (
                <li key={person.id}>
                  <ContactOutreachEditor
                    contact={person}
                    onSaved={onContactSaved}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function ContactOutreachEditor({
  contact,
  onSaved,
}: {
  contact: CompanyContact;
  onSaved?: (contact: CompanyContact) => void;
}) {
  const [draft, setDraft] = useState(contact.generated_email_body ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const canSend = isUsableEmailStatus(contact.email_status);

  useEffect(() => {
    setDraft(contact.generated_email_body ?? "");
  }, [contact.id, contact.generated_email_body]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await saveContactEmail(contact.id, draft);
      onSaved?.(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Taslak kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-line px-3 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium text-ink">
            <UserRound className="size-3.5 shrink-0 text-ink-muted" strokeWidth={2} />
            {contact.name ?? "İsimsiz"}
            {contact.title ? ` · ${contact.title}` : ""}
            {contact.is_selected ? (
              <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[10px] font-medium text-brand-deep">
                Seçilen persona
              </span>
            ) : null}
            {contact.persona_rank ? (
              <span className="text-[10px] text-ink-muted">{contact.persona_rank} puan</span>
            ) : null}
          </p>
          {contact.email ? (
            <a
              href={`mailto:${contact.email}`}
              className="mt-0.5 inline-flex items-center gap-1 text-[12px] text-brand hover:underline"
            >
              <Mail className="size-3" strokeWidth={2} />
              {contact.email}
            </a>
          ) : (
            <p className="mt-0.5 text-[12px] text-ink-muted">E-posta yok</p>
          )}
        </div>
        <EmailStatusBadge status={contact.email_status} />
      </div>

      <label className="mt-3 block">
        <span className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">
          Soğuk e-posta taslağı
        </span>
        <textarea
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setSaved(false);
          }}
          rows={7}
          placeholder={
            canSend
              ? "Doğrulanmış adres için taslak burada görünür. Göndermeden önce düzenleyin."
              : "E-posta doğrulanmadan taslak üretilmez."
          }
          className="mt-1 w-full resize-y rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] leading-relaxed text-ink outline-none focus:border-brand"
        />
      </label>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-ink-muted">
          Gönderim henüz yok. Taslağı gözden geçirip kaydedin.
        </p>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="rounded-lg bg-ink px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-brand-deep disabled:opacity-50"
        >
          {saving ? "Kaydediliyor…" : saved ? "Kaydedildi" : "Taslağı kaydet"}
        </button>
      </div>
      {error ? <p className="mt-1 text-[11px] text-danger">{error}</p> : null}
    </div>
  );
}

function ScoreTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line-soft px-3 py-2">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-[16px] font-semibold tabular text-ink">{value}</dd>
    </div>
  );
}
