import type { ReactNode } from "react";

/** Shared section shell: consistent rhythm, optional eyebrow + heading.
 *  Every section component renders through this so vertical spacing and
 *  max-width stay uniform across the whole generated site. */
export default function Section({
  id,
  eyebrow,
  heading,
  sub,
  children,
  tight = false,
}: {
  id?: string;
  eyebrow?: string;
  heading?: string;
  sub?: string;
  children: ReactNode;
  tight?: boolean;
}) {
  return (
    <section id={id} className={tight ? "py-14" : "py-20 md:py-28"}>
      <div className="mx-auto max-w-6xl px-5">
        {(eyebrow || heading || sub) && (
          <div className="mb-12 max-w-2xl">
            {eyebrow && (
              <p className="mb-3 text-sm font-medium uppercase tracking-widest text-accent">
                {eyebrow}
              </p>
            )}
            {heading && (
              <h2 className="font-heading text-3xl font-semibold tracking-tight text-text md:text-4xl">
                {heading}
              </h2>
            )}
            {sub && <p className="mt-4 text-lg leading-relaxed text-muted">{sub}</p>}
          </div>
        )}
        {children}
      </div>
    </section>
  );
}
