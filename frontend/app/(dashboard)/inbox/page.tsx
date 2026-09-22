import type { Metadata } from "next";

import { InboxView } from "@/components/replies/InboxView";

export const metadata: Metadata = {
  title: "Gelen Kutusu",
  description: "AI tarafından sınıflandırılmış gelen e-posta yanıtları.",
};

export default function InboxPage() {
  return <InboxView />;
}
