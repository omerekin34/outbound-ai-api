import type { Metadata } from "next";

import { DiscoveryView } from "@/components/discovery/DiscoveryView";

export const metadata: Metadata = {
  title: "Keşif",
  description: "Domain girerek şirket araştırma hattını arka planda başlatın.",
};

export default function KesifPage() {
  return <DiscoveryView />;
}
