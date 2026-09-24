import type { Metadata } from "next";
import { Suspense } from "react";

import { CompaniesView } from "@/components/companies/CompaniesView";
import { ReplyTableSkeleton } from "@/components/replies/ReplyStates";

export const metadata: Metadata = {
  title: "Şirketler",
  description: "Analiz edilmiş şirketler, puanlar, kanıtlar ve karar vericiler.",
};

export default function SirketlerPage() {
  return (
    <Suspense fallback={<ReplyTableSkeleton rows={5} />}>
      <CompaniesView />
    </Suspense>
  );
}
