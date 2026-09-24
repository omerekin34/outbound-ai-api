import { Suspense } from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

/** Kenar çubuğu + üst bar: tüm panel sayfaları bu kabuğu paylaşır. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Suspense fallback={<div className="h-14 shrink-0 border-b border-line bg-canvas" />}>
          <Topbar />
        </Suspense>
        <main className="flex-1 overflow-y-auto px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
