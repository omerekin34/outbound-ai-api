import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/Card";

export interface StatTile {
  key: string;
  label: string;
  /** Hazır biçimlendirilmiş değer ("12", "%86,8", "—"). */
  value: string;
  icon: LucideIcon;
  tone?: "brand" | "accent";
  caption: string;
}

/** Genel Bakış'taki metrik kartlarıyla aynı görsel dil. */
export function StatTiles({ tiles }: { tiles: StatTile[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {tiles.map((tile) => {
        const Icon = tile.icon;

        return (
          <Card key={tile.key} className="p-4">
            <div className="flex items-center gap-2">
              <span
                className={`flex size-7 items-center justify-center rounded-lg ${
                  tile.tone === "accent"
                    ? "bg-accent-soft text-accent"
                    : "bg-brand-soft text-brand"
                }`}
              >
                <Icon className="size-3.5" strokeWidth={2} />
              </span>
              <p className="truncate text-[12px] text-ink-soft">{tile.label}</p>
            </div>

            <p className="tabular mt-2.5 text-[28px] leading-none font-semibold tracking-tight text-ink">
              {tile.value}
            </p>
            <p className="mt-2 text-[11px] text-ink-muted">{tile.caption}</p>
          </Card>
        );
      })}
    </div>
  );
}
