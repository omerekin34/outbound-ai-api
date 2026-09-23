import type { Metadata } from "next";

import { OpportunitiesView } from "@/components/replies/OpportunitiesView";

export const metadata: Metadata = {
  title: "Fırsatlar",
  description: "Nitelikli şirketler, Apollo karar vericileri ve olumlu yanıtlar.",
};

export default function FirsatlarPage() {
  return <OpportunitiesView />;
}
