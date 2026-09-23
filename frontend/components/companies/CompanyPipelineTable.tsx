"use client";

import { Mail, UserRound } from "lucide-react";
import { useState } from "react";

import { CompanyDetailModal } from "@/components/companies/CompanyDetailModal";
import { EmailStatusBadge } from "@/components/companies/EmailStatusBadge";
import { Card } from "@/components/ui/Card";
import type { CompanyContact, CompanyRow } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  new: "Yeni",
  pending: "Bekliyor",
  qualified: "Nitelikli",
  "high priority": "Yüksek öncelik",
  "low priority": "Düşük öncelik",
  reject: "Red",
  review: "İnceleme",
};

function scoreLabel(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
}

export function CompanyPipelineTable({
  items,
  emptyMessage = "Henüz şirket yok. Keşif veya n8n bir domain gönderdiğinde burada görünür.",
  onRefresh,
}: {
  items: CompanyRow[];
  emptyMessage?: string;
  onRefresh?: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, CompanyContact>>({});
  const rows = items.map((company) => ({
    ...company,
    contacts: company.contacts.map((person) => edits[person.id] ?? person),
  }));
  const selected = rows.find((item) => item.id === selectedId) ?? null;

  if (items.length === 0) {
    return (
      <Card className="p-8">
        <p className="text-center text-[12px] text-ink-soft">{emptyMessage}</p>
      </Card>
    );
  }

  return (
    <>
    <Card className="p-4">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[960px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <Th className="w-[20%]">Şirket</Th>
              <Th className="w-[72px]">ICP</Th>
              <Th className="w-[72px]">Need</Th>
              <Th className="w-[16%]">ERP</Th>
              <Th>Ağrı hipotezi</Th>
              <Th className="w-[20%]">Karar verici</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((company) => {
              const status =
                company.qualification_status ?? company.status ?? "";
              return (
                <tr
                  key={company.id}
                  className="cursor-pointer border-b border-line-soft align-top hover:bg-canvas"
                  onClick={() => setSelectedId(company.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(company.id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td className="px-3 py-3">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {company.name ?? company.domain ?? "İsimsiz şirket"}
                    </p>
                    <p className="truncate text-[11px] text-ink-muted">
                      {company.domain ?? "—"}
                      {status
                        ? ` · ${STATUS_LABEL[status] ?? status}`
                        : ""}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-[13px] font-semibold text-ink">
                    {scoreLabel(company.icp_score)}
                  </td>
                  <td className="px-3 py-3 text-[13px] font-semibold text-ink">
                    {scoreLabel(company.need_score)}
                  </td>
                  <td className="px-3 py-3">
                    {company.erp_signal && company.erp_signal !== "unknown" ? (
                      <span className="inline-flex rounded-md bg-brand-soft px-1.5 py-0.5 text-[11px] font-medium text-brand-deep">
                        {company.erp_signal}
                        {company.erp_evidence_count
                          ? ` · ${company.erp_evidence_count}`
                          : ""}
                      </span>
                    ) : (
                      <span className="text-[11px] text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {company.pain_hypothesis ? (
                      <p className="line-clamp-3 text-[12px] leading-relaxed text-ink">
                        {company.pain_hypothesis}
                      </p>
                    ) : (
                      <span className="text-[11px] text-ink-muted">
                        {company.requires_deep_research
                          ? "Derin araştırma bekleniyor"
                          : "Yalnızca nitelikli şirketlerde üretilir"}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {company.contacts.length === 0 ? (
                      <span className="text-[11px] text-ink-muted">
                        Apollo kişisi yok
                      </span>
                    ) : (
                      <ul className="space-y-1.5">
                        {company.contacts.slice(0, 3).map((person) => (
                          <li
                            key={person.id}
                            className="flex items-start gap-1.5"
                          >
                            <UserRound
                              className="mt-0.5 size-3 shrink-0 text-ink-muted"
                              strokeWidth={2}
                            />
                            <div className="min-w-0">
                              <p className="truncate text-[12px] font-medium text-ink">
                                {person.name ?? "İsimsiz"}
                                {person.title ? ` · ${person.title}` : ""}
                              </p>
                              <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                                <EmailStatusBadge status={person.email_status} />
                                {person.email ? (
                                  <a
                                    href={`mailto:${person.email}`}
                                    onClick={(event) => event.stopPropagation()}
                                    className="inline-flex items-center gap-1 truncate text-[11px] text-brand hover:underline"
                                  >
                                    <Mail className="size-3" strokeWidth={2} />
                                    {person.email}
                                  </a>
                                ) : null}
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
    {selected ? (
      <CompanyDetailModal
        company={selected}
        onClose={() => setSelectedId(null)}
        onContactSaved={(contact) => {
          setEdits((current) => ({ ...current, [contact.id]: contact }));
          onRefresh?.();
        }}
      />
    ) : null}
    </>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={`px-3 py-2 text-[11px] font-medium tracking-wide text-ink-muted uppercase ${className}`}
    >
      {children}
    </th>
  );
}
