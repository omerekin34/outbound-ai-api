import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

/** Tasarımdaki beyaz, ince kenarlıklı panel. */
export function Card({ children, className = "" }: CardProps) {
  return (
    <section
      className={`rounded-card border border-line bg-surface shadow-[0_1px_2px_rgba(22,36,31,0.04)] ${className}`}
    >
      {children}
    </section>
  );
}

interface CardTitleProps {
  children: ReactNode;
  className?: string;
}

export function CardTitle({ children, className = "" }: CardTitleProps) {
  return (
    <h2
      className={`text-[13px] font-semibold tracking-tight text-ink ${className}`}
    >
      {children}
    </h2>
  );
}
