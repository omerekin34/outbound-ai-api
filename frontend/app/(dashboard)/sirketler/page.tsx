import type { Metadata } from "next";

import { CompaniesView } from "@/components/companies/CompaniesView";

export const metadata: Metadata = {
  title: "Şirketler",
  description: "Analiz edilmiş şirketler, puanlar, kanıtlar ve karar vericiler.",
};

export default function SirketlerPage() {
  return <CompaniesView />;
}
