import { Card } from "@/components/ui/Card";

function Bar({ className = "" }: { className?: string }) {
  return (
    <span
      className={`block animate-pulse rounded bg-line-soft ${className}`}
      aria-hidden
    />
  );
}

/** İlk yükleme sırasında gerçek yerleşimi koruyan iskelet. */
export function DashboardSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <span className="sr-only">Dashboard verileri yükleniyor…</span>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index} className="p-4">
            <Bar className="size-7 rounded-lg" />
            <Bar className="mt-3 h-7 w-20" />
            <Bar className="mt-3 h-3 w-24" />
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card className="p-4">
            <Bar className="h-3 w-24" />
            <Bar className="mt-4 h-12 w-full" />
          </Card>
          <Card className="p-4">
            <Bar className="h-3 w-28" />
            <Bar className="mt-4 h-32 w-full" />
          </Card>
        </div>
        <Card className="p-4">
          <Bar className="h-3 w-32" />
          <Bar className="mt-4 h-14 w-full" />
          <Bar className="mt-2 h-14 w-full" />
        </Card>
      </div>
    </div>
  );
}
