"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3 } from "lucide-react";

import { NAV_ITEMS } from "./nav";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-[236px] shrink-0 flex-col border-r border-line bg-sidebar">
      <div className="flex items-center gap-2.5 px-6 pt-6 pb-7">
        <BarChart3 className="size-5 text-brand" strokeWidth={2.4} />
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-tight text-ink">
            Revenue
          </p>
          <p className="text-[11px] text-ink-muted">Satış kontrol merkezi</p>
        </div>
      </div>

      <nav className="flex-1 px-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
                    isActive
                      ? "bg-brand font-semibold text-on-brand"
                      : "text-ink-soft hover:bg-line-soft hover:text-ink"
                  }`}
                >
                  <Icon
                    className={`size-4 ${isActive ? "text-on-brand" : "text-ink-muted"}`}
                    strokeWidth={1.9}
                  />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="flex items-center gap-2.5 px-6 py-5">
        <span className="flex size-7 items-center justify-center rounded-full bg-brand text-[11px] font-semibold text-on-brand">
          S
        </span>
        <div className="leading-tight">
          <p className="text-[12px] font-semibold text-ink">Siz</p>
          <p className="text-[11px] text-ink-muted">Tek kullanıcı</p>
        </div>
      </div>
    </aside>
  );
}
