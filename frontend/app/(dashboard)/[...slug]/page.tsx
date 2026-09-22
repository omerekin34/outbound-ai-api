import { notFound } from "next/navigation";

import { NAV_ITEMS } from "@/components/layout/nav";
import { Card } from "@/components/ui/Card";

/**
 * Kenar çubuğundaki henüz yapılmamış sayfalar için ortak yer tutucu.
 *
 * Yalnızca `NAV_ITEMS` içinde tanımlı adresler karşılanır; bilinmeyen adresler
 * normal şekilde 404 döner.
 */
export default async function PlaceholderPage(
  props: PageProps<"/[...slug]">,
) {
  const { slug } = await props.params;
  const href = `/${(slug ?? []).join("/")}`;
  const navItem = NAV_ITEMS.find((item) => item.href === href);

  if (!navItem) {
    notFound();
  }

  const Icon = navItem.icon;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight text-ink">
          {navItem.label}
        </h1>
        <p className="mt-1 text-[13px] text-ink-soft">
          Bu bölüm henüz hazır değil.
        </p>
      </div>

      <Card className="p-10">
        <div className="mx-auto flex max-w-sm flex-col items-center gap-3 text-center">
          <span className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <Icon className="size-5" strokeWidth={1.9} />
          </span>
          <h2 className="text-[14px] font-semibold text-ink">
            {navItem.label} yakında
          </h2>
          <p className="text-[12px] leading-relaxed text-ink-soft">
            Genel Bakış ekranı canlı verilerle çalışıyor. Bu bölüm backend
            tarafında ilgili uç noktalar hazırlandığında doldurulacak.
          </p>
        </div>
      </Card>
    </div>
  );
}
