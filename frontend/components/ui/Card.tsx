import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  id?: string;
}

/** Tasarımdaki beyaz, ince kenarlıklı panel. */
export function Card({ children, className = "", id }: CardProps) {
  return (
    <section
      id={id}
      className={`rounded-card border border-line bg-surface shadow-[0_12px_32px_rgba(0,0,0,0.28)] ${className}`}
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
