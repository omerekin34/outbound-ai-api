export type EmailStatus =
  | "valid"
  | "invalid"
  | "accept_all"
  | "unknown"
  | "risky"
  | "verified"
  | "catch-all"
  | "unverified"
  | "bounced"
  | string
  | null
  | undefined;

const LABEL: Record<string, string> = {
  valid: "Valid",
  invalid: "Invalid",
  accept_all: "Accept-all",
  unknown: "Unknown",
  risky: "Risky",
  verified: "Valid",
  "catch-all": "Accept-all",
  unverified: "Unknown",
  bounced: "Invalid",
};

const TONE: Record<string, string> = {
  valid: "bg-brand-soft text-brand-deep",
  verified: "bg-brand-soft text-brand-deep",
  accept_all: "bg-accent-soft text-accent",
  "catch-all": "bg-accent-soft text-accent",
  unknown: "bg-line-soft text-ink-muted",
  unverified: "bg-line-soft text-ink-muted",
  invalid: "bg-danger-soft text-danger",
  bounced: "bg-danger-soft text-danger",
  risky: "bg-danger-soft text-danger",
};

export function isUsableEmailStatus(status: EmailStatus): boolean {
  return status === "valid";
}

export function EmailStatusBadge({ status }: { status: EmailStatus }) {
  if (!status) {
    return (
      <span className="inline-flex rounded-md bg-line-soft px-1.5 py-0.5 text-[10px] font-medium text-ink-muted">
        Bekliyor
      </span>
    );
  }
  return (
    <span
      className={`inline-flex rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
        TONE[status] ?? "bg-line-soft text-ink-muted"
      }`}
    >
      {LABEL[status] ?? status}
    </span>
  );
}
