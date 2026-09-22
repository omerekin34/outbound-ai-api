import type { Metadata } from "next";

import { OpportunitiesView } from "@/components/replies/OpportunitiesView";

export const metadata: Metadata = {
  title: "Fırsatlar",
  description: "AI'ın olumlu sınıflandırdığı yanıtlardan oluşan fırsat listesi.",
};

export default function OpportunitiesPage() {
  return <OpportunitiesView />;
}
