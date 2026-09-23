"use client";

import { Building2 } from "lucide-react";
import { useState } from "react";

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

export function CompaniesView({
  qualifiedOnly = false,
  title = "Şirketler",
  subtitle = "ICP, Need, ERP sinyali, ağrı hipotezi ve Apollo kişileri Neon’dan gelir.",
}: {
  qualifiedOnly?: boolean;
  title?: string;
  subtitle?: string;
}) {
  const [search, setSearch] = useState("");
  const { data, error, isLoading, isRefreshing, refresh } = useCompanies({
    limit: 50,
    offset: 0,
    search: search.trim() || null,
    qualifiedOnly,
  });

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
          onChange={setSearch}
          placeholder="Şirket veya domain ara"
        />
      </PageHeader>

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
            {formatNumber(data.total)} şirket
          </p>
          {data.items.length === 0 && search.trim() ? (
            <EmptyState
              icon={Building2}
              title="Sonuç yok"
              description={`“${search.trim()}” ile eşleşen şirket bulunamadı.`}
            />
          ) : (
            <CompanyPipelineTable items={data.items} onRefresh={refresh} />
          )}
        </>
      ) : null}
    </div>
  );
}
