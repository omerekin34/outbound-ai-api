import {
  Building2,
  Calendar,
  Cpu,
  FileText,
  Inbox,
  LayoutDashboard,
  Megaphone,
  Search,
  Settings,
  Target,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

/** Kenar çubuğu sırası tasarımdaki sırayı birebir izler. */
export const NAV_ITEMS: NavItem[] = [
  { label: "Genel Bakış", href: "/", icon: LayoutDashboard },
  { label: "Keşif", href: "/kesif", icon: Search },
  { label: "Şirketler", href: "/sirketler", icon: Building2 },
  { label: "Kampanyalar", href: "/kampanyalar", icon: Megaphone },
  { label: "Gelen Kutusu", href: "/inbox", icon: Inbox },
  { label: "Demolar", href: "/demolar", icon: Calendar },
  { label: "Fırsatlar", href: "/firsatlar", icon: Target },
  { label: "Teklifler", href: "/teklifler", icon: FileText },
  { label: "AI Operasyon", href: "/ai-operasyon", icon: Cpu },
  { label: "Ayarlar", href: "/ayarlar", icon: Settings },
];

export function findNavItem(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) => item.href === pathname);
}
