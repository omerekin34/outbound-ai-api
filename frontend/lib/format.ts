const numberFormatter = new Intl.NumberFormat("tr-TR");

const currencyFormatter = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 0,
});

const timeFormatter = new Intl.DateTimeFormat("tr-TR", {
  hour: "2-digit",
  minute: "2-digit",
});

const dateTimeFormatter = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return numberFormatter.format(value);
}

export function formatCurrency(value: number): string {
  return currencyFormatter.format(value);
}

/** Aktivite satırlarındaki "14:32" biçimi. */
export function formatTime(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? "--:--" : timeFormatter.format(date);
}

export function formatDateTime(date: Date): string {
  return dateTimeFormatter.format(date);
}

/** "3 sn önce", "12 dk önce" gibi göreli zaman. */
export function formatRelative(isoDate: string, now = Date.now()): string {
  const timestamp = new Date(isoDate).getTime();
  if (Number.isNaN(timestamp)) {
    return "";
  }

  const seconds = Math.max(0, Math.round((now - timestamp) / 1000));
  if (seconds < 60) return `${seconds} sn önce`;

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} dk önce`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;

  return `${Math.round(hours / 24)} gün önce`;
}

/** Süreyi okunur hale getirir: 520 -> "0,5 sn". */
export function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null) return null;
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toLocaleString("tr-TR", {
    maximumFractionDigits: 1,
  })} sn`;
}
