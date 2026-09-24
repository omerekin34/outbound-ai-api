"use client";

import { FormEvent, KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Building2, Search } from "lucide-react";
import useSWR from "swr";

import { fetchCompanies, type CompanyRow } from "@/lib/api";

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

function useDebounced(value: string, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function rankMatches(items: CompanyRow[], term: string): CompanyRow[] {
  const needle = term.toLowerCase();
  return [...items].sort((left, right) => {
    const score = (row: CompanyRow) => {
      const name = (row.name ?? "").toLowerCase();
      const domain = (row.domain ?? "").toLowerCase();
      if (domain.startsWith(needle) || name.startsWith(needle)) return 0;
      if (domain.includes(needle) || name.includes(needle)) return 1;
      return 2;
    };
    return score(left) - score(right);
  });
}

function Highlight({ text, query }: { text: string; query: string }) {
  const index = text.toLowerCase().indexOf(query.toLowerCase());
  if (index < 0 || !query) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-[3px] bg-brand/20 text-brand">
        {text.slice(index, index + query.length)}
      </mark>
      {text.slice(index + query.length)}
    </>
  );
}

export function CompanySearch() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const listId = useId();
  const wrapRef = useRef<HTMLFormElement>(null);
  const [query, setQuery] = useState(initialQuery);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const trimmed = query.trim();
  const deferred = useDebounced(trimmed, 80);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  const shouldFetch = open && deferred.length >= 1;
  const { data, isLoading } = useSWR(
    shouldFetch ? (["company-typeahead", deferred] as const) : null,
    ([, term]) => fetchCompanies({ search: term, limit: 8 }),
    { keepPreviousData: true, dedupingInterval: 200 },
  );

  const results = useMemo(
    () => rankMatches(data?.items ?? [], deferred),
    [data?.items, deferred],
  );
  const total = data?.total ?? 0;

  useEffect(() => {
    setActive(0);
  }, [deferred]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  function listHref(term: string) {
    return term ? `/sirketler?q=${encodeURIComponent(term)}` : "/sirketler";
  }

  function companyHref(company: CompanyRow) {
    const term = company.domain || company.name || trimmed;
    return `/sirketler?q=${encodeURIComponent(term)}&company=${encodeURIComponent(company.id)}`;
  }

  function go(href: string) {
    setOpen(false);
    window.location.assign(href);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = results[active];
    if (open && selected) {
      go(companyHref(selected));
      return;
    }
    const term = String(new FormData(event.currentTarget).get("q") ?? "").trim();
    go(listHref(term));
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index - 1 + results.length) % results.length);
    }
  }

  const waiting = trimmed !== deferred;
  const showPanel = open && trimmed.length >= 1;

  return (
    <form
      ref={wrapRef}
      action="/sirketler"
      method="get"
      onSubmit={onSubmit}
      className="relative w-full max-w-[360px]"
    >
      <button
        type="submit"
        aria-label="Ara"
        className="absolute top-1/2 left-1.5 z-10 flex size-5 -translate-y-1/2 items-center justify-center rounded-full text-ink-muted transition-colors hover:text-ink"
      >
        <Search className="size-3.5" />
      </button>
      <input
        type="search"
        name="q"
        value={query}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={showPanel}
        aria-controls={listId}
        aria-activedescendant={
          showPanel && results[active] ? `${listId}-${results[active].id}` : undefined
        }
        role="combobox"
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(event.target.value.trim().length > 0);
        }}
        onFocus={() => {
          if (trimmed.length > 0) setOpen(true);
        }}
        onKeyDown={onKeyDown}
        placeholder="Şirket veya domain ara..."
        aria-label="Şirket ara"
        className="h-8 w-full rounded-full border border-line bg-surface pr-3 pl-9 text-[12px] text-ink placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
      />

      {showPanel ? (
        <div
          id={listId}
          role="listbox"
          className="absolute top-[calc(100%+6px)] left-0 z-50 w-[min(420px,calc(100vw-2rem))] overflow-hidden rounded-xl border border-line bg-surface shadow-[0_16px_40px_rgba(0,0,0,0.45)]"
        >
          {(isLoading || waiting) && results.length === 0 ? (
            <p className="px-3 py-2.5 text-[12px] text-ink-muted">Aranıyor…</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2.5 text-[12px] text-ink-muted">
              “{trimmed}” ile eşleşen şirket yok.
            </p>
          ) : (
            <ul>
              {results.map((company, index) => {
                const title = company.name || company.domain || "İsimsiz şirket";
                const subtitle = company.domain && company.name ? company.domain : company.website;
                const status =
                  STATUS_LABEL[company.qualification_status ?? ""] ??
                  STATUS_LABEL[company.status ?? ""] ??
                  company.qualification_status ??
                  company.status;
                return (
                  <li key={company.id} role="presentation">
                    <a
                      href={companyHref(company)}
                      id={`${listId}-${company.id}`}
                      role="option"
                      aria-selected={index === active}
                      onMouseEnter={() => setActive(index)}
                      className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                        index === active ? "bg-brand-soft" : "hover:bg-canvas"
                      }`}
                    >
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-line bg-canvas text-ink-muted">
                        <Building2 className="size-3.5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] font-medium text-ink">
                          <Highlight text={title} query={trimmed} />
                        </span>
                        {subtitle ? (
                          <span className="block truncate text-[11px] text-ink-muted">
                            <Highlight text={subtitle} query={trimmed} />
                          </span>
                        ) : null}
                      </span>
                      {status ? (
                        <span className="shrink-0 rounded-full border border-line px-1.5 py-0.5 text-[10px] text-ink-soft">
                          {status}
                        </span>
                      ) : null}
                    </a>
                  </li>
                );
              })}
            </ul>
          )}
          <a
            href={listHref(trimmed)}
            className="flex w-full items-center justify-between border-t border-line px-3 py-2 text-[11px] text-ink-soft hover:bg-canvas hover:text-brand"
          >
            <span>Tüm sonuçları gör</span>
            {total > 0 ? <span className="tabular">{total}</span> : null}
          </a>
        </div>
      ) : null}
    </form>
  );
}
