export interface PageHeaderProps {
  heading: string;
  sub?: string;
}

/** Interior-page title block. The project writer injects this on any page
 *  whose plan has no Hero/DocsLayout, so every page carries exactly one h1
 *  — heading hierarchy is a generator invariant, not a hope. */
export default function PageHeader({ heading, sub }: PageHeaderProps) {
  return (
    <section className="hero-wash">
      <div className="mx-auto max-w-6xl px-5 pb-10 pt-20 md:pt-28">
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-text md:text-5xl">
          {heading}
        </h1>
        {sub && <p className="mt-4 max-w-2xl text-lg text-muted">{sub}</p>}
      </div>
    </section>
  );
}
