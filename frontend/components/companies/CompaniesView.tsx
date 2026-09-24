"use client";

import { Building2, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CompanyPipelineTable } from "@/components/companies/CompanyPipelineTable";
import { SearchInput } from "@/components/replies/SearchInput";
import {
  ConnectionError,
  EmptyState,
  ReplyTableSkeleton,
  StaleWarning,
} from "@/components/replies/ReplyStates";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatNumber } from "@/lib/format";
import { useCompanies } from "@/lib/useCompanies";

const QUALIFIED_FILTERS = new Set(["qualified", "nitelikli"]);

export function CompaniesView({
  title = "Şirketler",
  subtitle = "ICP, Need, ERP sinyali, ağrı hipotezi ve Apollo kişileri Neon’dan gelir.",
}: {
  title?: string;
  subtitle?: string;
}) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filter = (searchParams.get("filter") ?? "").trim().toLowerCase();
  const qualifiedOnly = QUALIFIED_FILTERS.has(filter);
  const queryFromUrl = searchParams.get("q") ?? "";
  const openCompanyId = searchParams.get("company");

  const [search, setSearch] = useState(queryFromUrl);
  const { data, error, isLoading, isRefreshing, refresh } = useCompanies({
    limit: 50,
    offset: 0,
    search: search.trim() || null,
    qualifiedOnly,
  });

  useEffect(() => {
    setSearch(queryFromUrl);
  }, [queryFromUrl]);

  function replaceParams(mutate: (params: URLSearchParams) => void) {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function setSearchQuery(value: string) {
    setSearch(value);
    replaceParams((params) => {
      const trimmed = value.trim();
      if (trimmed) params.set("q", trimmed);
      else params.delete("q");
    });
  }

  function setOpenCompany(id: string | null) {
    replaceParams((params) => {
      if (id) params.set("company", id);
      else params.delete("company");
    });
  }

  function setQualifiedFilter(enabled: boolean) {
    replaceParams((params) => {
      if (enabled) params.set("filter", "qualified");
      else params.delete("filter");
    });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={title}
        subtitle={subtitle}
        isRefreshing={isRefreshing}
        onRefresh={refresh}
      >
        <SearchInput
          value={search}
          onChange={setSearchQuery}
          placeholder="Şirket veya domain ara"
        />
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2">
        <FilterChip
          label="Tümü"
          isActive={!qualifiedOnly}
          onClick={() => setQualifiedFilter(false)}
        />
        <FilterChip
          label="Nitelikli"
          isActive={qualifiedOnly}
          onClick={() => setQualifiedFilter(!qualifiedOnly)}
        />
        {qualifiedOnly ? (
          <button
            type="button"
            onClick={() => setQualifiedFilter(false)}
            className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand"
          >
            Filtreyi temizle
            <X className="size-3" strokeWidth={2} />
          </button>
        ) : null}
      </div>

      {error && data ? <StaleWarning message={error} /> : null}
      {isLoading ? <ReplyTableSkeleton rows={5} /> : null}

      {!isLoading && error && !data ? (
        <ConnectionError
          message={error}
          onRetry={refresh}
          endpoint="/api/companies"
        />
      ) : null}

      {data ? (
        <>
          <p className="text-[12px] text-ink-soft">
            {formatNumber(data.total)}{" "}
            {qualifiedOnly ? "nitelikli şirket" : "şirket"}
          </p>
          {data.items.length === 0 && (search.trim() || qualifiedOnly) ? (
            <EmptyState
              icon={Building2}
              title="Sonuç yok"
              description={
                search.trim()
                  ? `“${search.trim()}” ile eşleşen şirket bulunamadı.`
                  : "Bu filtreye uyan nitelikli şirket yok. Filtreyi temizleyerek tüm kayıtları görebilirsiniz."
              }
            />
          ) : (
            <CompanyPipelineTable
              items={data.items}
              onRefresh={refresh}
              openCompanyId={openCompanyId}
              onOpenCompanyChange={setOpenCompany}
            />
          )}
        </>
      ) : null}
    </div>
  );
}

function FilterChip({
  label,
  isActive,
  onClick,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        isActive
          ? "border-brand bg-brand text-on-brand"
          : "border-line bg-surface text-ink-soft hover:border-brand hover:text-brand"
      }`}
    >
      {label}
    </button>
  );
}
