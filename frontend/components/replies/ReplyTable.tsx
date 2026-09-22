"use client";

import {
  ChevronDown,
  Building2,
  Mail,
  Sparkles,
  Target,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import { ClassificationBadge } from "@/components/replies/ClassificationBadge";
import { formatNumber, formatRelative } from "@/lib/format";
import type { Reply } from "@/lib/api";

interface ReplyTableProps {
  items: Reply[];
  /** Fırsatlar ekranında şirket puanı kolonu gösterilir. */
  showScore?: boolean;
  /** Okundu/okunmadı değiştirme; verilmezse buton çıkmaz. */
  onToggleRead?: (reply: Reply) => void;
}

export function ReplyTable({
  items,
  showScore = false,
  onToggleRead,
}: ReplyTableProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            <Th className="w-[22%]">Şirket</Th>
            <Th className="w-[22%]">Karar verici</Th>
            <Th>Yanıt</Th>
            <Th className="w-[150px]">AI sınıfı</Th>
            {showScore ? <Th className="w-[80px] text-right">Puan</Th> : null}
            <Th className="w-[110px] text-right">Geldi</Th>
          </tr>
        </thead>

        <tbody>
          {items.map((reply) => {
            const isExpanded = expandedId === reply.id;

            return (
              <ReplyRow
                key={reply.id}
                reply={reply}
                isExpanded={isExpanded}
                showScore={showScore}
                onToggle={() => setExpandedId(isExpanded ? null : reply.id)}
                onToggleRead={onToggleRead}
              />
            );
          })}
        </tbody>
      </table>
    </div>
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

interface ReplyRowProps {
  reply: Reply;
  isExpanded: boolean;
  showScore: boolean;
  onToggle: () => void;
  onToggleRead?: (reply: Reply) => void;
}

function ReplyRow({
  reply,
  isExpanded,
  showScore,
  onToggle,
  onToggleRead,
}: ReplyRowProps) {
  const columnCount = showScore ? 6 : 5;

  return (
    <>
      <tr
        onClick={onToggle}
        aria-expanded={isExpanded}
        className={`cursor-pointer border-b border-line-soft align-top transition-colors hover:bg-canvas ${
          isExpanded ? "bg-canvas" : ""
        }`}
      >
        {/* Şirket */}
        <td className="px-3 py-3">
          <div className="flex items-start gap-2">
            {/* Okunmamış yanıtlar için nokta işareti. */}
            <span
              className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                reply.is_read ? "bg-transparent" : "bg-brand"
              }`}
              aria-label={reply.is_read ? undefined : "Okunmadı"}
            />
            <div className="min-w-0">
              <p
                className={`truncate text-[13px] text-ink ${
                  reply.is_read ? "font-medium" : "font-semibold"
                }`}
              >
                {reply.company_name ?? "Bilinmeyen şirket"}
              </p>
              <p className="truncate text-[11px] text-ink-muted">
                {reply.company_domain ?? reply.company_industry ?? "—"}
              </p>
            </div>
          </div>
        </td>

        {/* Karar verici: ad + ünvan */}
        <td className="px-3 py-3">
          {reply.contact_name ? (
            <>
              <p className="truncate text-[13px] font-medium text-ink">
                {reply.contact_name}
              </p>
              <p className="truncate text-[11px] text-ink-soft">
                {reply.contact_title ?? "Ünvan bilinmiyor"}
              </p>
            </>
          ) : (
            <p className="text-[12px] text-ink-muted">Eşleşen kişi yok</p>
          )}
        </td>

        {/* Yanıt önizlemesi */}
        <td className="px-3 py-3">
          {reply.subject ? (
            <p className="truncate text-[12px] font-medium text-ink">
              {reply.subject}
            </p>
          ) : null}
          <p className="mt-0.5 line-clamp-2 text-[12px] leading-relaxed text-ink-soft">
            {reply.snippet}
          </p>
        </td>

        {/* AI sınıflandırması */}
        <td className="px-3 py-3">
          <ClassificationBadge
            classification={reply.classification}
            confidence={reply.confidence}
            showConfidence
          />
        </td>

        {showScore ? (
          <td className="tabular px-3 py-3 text-right text-[13px] font-semibold text-ink">
            {reply.overall_score === null
              ? "—"
              : formatNumber(Math.round(reply.overall_score))}
          </td>
        ) : null}

        <td className="px-3 py-3 text-right">
          <span className="text-[11px] whitespace-nowrap text-ink-muted">
            {formatRelative(reply.received_at)}
          </span>
          <ChevronDown
            className={`ml-1.5 inline size-3 text-ink-muted transition-transform ${
              isExpanded ? "rotate-180" : ""
            }`}
          />
        </td>
      </tr>

      {isExpanded ? (
        <tr className="border-b border-line-soft bg-canvas">
          <td colSpan={columnCount} className="px-3 pt-1 pb-4">
            <ExpandedReply reply={reply} onToggleRead={onToggleRead} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ExpandedReply({
  reply,
  onToggleRead,
}: {
  reply: Reply;
  onToggleRead?: (reply: Reply) => void;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      {/* AI'ın yakaladığı yanıtın birebir metni. */}
      <div className="rounded-xl border border-line bg-surface p-3.5">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-ink-muted">
          <Mail className="size-3.5" strokeWidth={2} />
          Yanıtın tam metni
        </div>
        {reply.subject ? (
          <p className="mt-2 text-[12px] font-semibold text-ink">
            {reply.subject}
          </p>
        ) : null}
        <p className="mt-1.5 text-[12px] leading-relaxed whitespace-pre-wrap text-ink-soft">
          {reply.body}
        </p>
        {reply.contact_email ? (
          <p className="mt-3 border-t border-line-soft pt-2 text-[11px] text-ink-muted">
            {reply.contact_email}
          </p>
        ) : null}
      </div>

      <div className="space-y-3">
        {reply.ai_summary || reply.ai_next_action ? (
          <div className="rounded-xl border border-brand-soft bg-brand-soft/40 p-3.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-brand">
              <Sparkles className="size-3.5" strokeWidth={2} />
              AI değerlendirmesi
            </div>
            {reply.ai_summary ? (
              <p className="mt-2 text-[12px] leading-relaxed text-ink">
                {reply.ai_summary}
              </p>
            ) : null}
            {reply.ai_next_action ? (
              <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-soft">
                <Target className="mt-0.5 size-3 shrink-0" strokeWidth={2} />
                {reply.ai_next_action}
              </p>
            ) : null}
          </div>
        ) : null}

        <dl className="rounded-xl border border-line bg-surface p-3.5 text-[11px]">
          <Detail icon={Building2} label="Şirket">
            {reply.company_name ?? "—"}
            {reply.company_city ? ` · ${reply.company_city}` : ""}
          </Detail>
          <Detail icon={UserRound} label="Karar verici">
            {reply.contact_name ?? "Eşleşen kişi yok"}
            {reply.contact_title ? ` · ${reply.contact_title}` : ""}
          </Detail>
        </dl>

        {onToggleRead ? (
          <button
            type="button"
            onClick={() => onToggleRead(reply)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand"
          >
            {reply.is_read ? "Okunmadı işaretle" : "Okundu işaretle"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Detail({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Building2;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 py-1">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-ink-muted" strokeWidth={2} />
      <div className="min-w-0">
        <dt className="text-ink-muted">{label}</dt>
        <dd className="text-[12px] text-ink">{children}</dd>
      </div>
    </div>
  );
}
