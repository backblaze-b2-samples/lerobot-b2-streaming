import type { ReactNode } from "react";

interface SectionProps {
  id: string;
  title: string;
  description?: string;
  children: ReactNode;
}

export function Section({ id, title, description, children }: SectionProps) {
  return (
    <section id={id} className="min-w-0 space-y-4">
      <div className="min-w-0">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {description && (
          <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
        )}
      </div>
      {children}
    </section>
  );
}

export function Row({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-border py-2 last:border-b-0 sm:grid-cols-[160px_1fr] sm:items-center sm:gap-4">
      <span className="text-xs font-mono text-muted-foreground">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
