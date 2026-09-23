import { Link, Mail, UserRound } from "lucide-react";

import { EmailStatusBadge } from "@/components/companies/EmailStatusBadge";
import { Card } from "@/components/ui/Card";
import type { DecisionMaker } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  qualified: "Nitelikli",
  "high priority": "Yüksek öncelik",
};

export function DecisionMakersTable({ items }: { items: DecisionMaker[] }) {
  if (items.length === 0) {
    return (
      <Card className="p-8">
        <p className="text-center text-[12px] text-ink-soft">
          Nitelikli şirketler için henüz Apollo’dan karar verici bulunamadı.
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <Th className="w-[24%]">Şirket</Th>
              <Th className="w-[24%]">Karar verici</Th>
              <Th>Ünvan</Th>
              <Th className="w-[220px]">İletişim</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((person) => (
              <tr key={person.id} className="border-b border-line-soft align-top">
                <td className="px-3 py-3">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {person.company_name ?? "Bilinmeyen şirket"}
                  </p>
                  <p className="truncate text-[11px] text-ink-muted">
                    {person.company_domain ?? "—"}
                    {person.company_status
                      ? ` · ${STATUS_LABEL[person.company_status] ?? person.company_status}`
                      : ""}
                  </p>
                </td>
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                      <UserRound className="size-3.5" strokeWidth={2} />
                    </span>
                    <p className="truncate text-[13px] font-semibold text-ink">
                      {person.name ?? "İsimsiz"}
                    </p>
                  </div>
                </td>
                <td className="px-3 py-3 text-[12px] text-ink-soft">
                  {person.title ?? "Ünvan bilinmiyor"}
                </td>
                <td className="px-3 py-3">
                  <div className="flex flex-col gap-1">
                    <EmailStatusBadge status={person.email_status} />
                    {person.email ? (
                      <a
                        href={`mailto:${person.email}`}
                        className="inline-flex items-center gap-1.5 truncate text-[12px] text-brand hover:underline"
                      >
                        <Mail className="size-3 shrink-0" strokeWidth={2} />
                        {person.email}
                      </a>
                    ) : (
                      <span className="text-[11px] text-ink-muted">E-posta yok</span>
                    )}
                    {person.linkedin_url ? (
                      <a
                        href={person.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-[11px] text-ink-soft hover:text-brand"
                      >
                        <Link className="size-3 shrink-0" strokeWidth={2} />
                        LinkedIn
                      </a>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
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
