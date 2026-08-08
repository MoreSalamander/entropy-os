import Reveal from "./Reveal";
import Section from "./Section";

export interface ProductShowcaseProps {
  eyebrow?: string;
  heading: string;
  sub?: string;
  /** Stylized product frame: window chrome + labeled panels. Pure SVG/CSS —
   *  an honest schematic stand-in until real product screens exist. */
  panels: { label: string; value: string }[];
  caption?: string;
}

export default function ProductShowcase({
  eyebrow,
  heading,
  sub,
  panels,
  caption,
}: ProductShowcaseProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading} sub={sub}>
      <Reveal>
        <figure className="overflow-hidden rounded-token border border-surface bg-surface shadow-2xl">
          <div className="flex items-center gap-1.5 border-b border-background/60 px-4 py-3">
            {[0, 1, 2].map((i) => (
              <span key={i} className="h-2.5 w-2.5 rounded-full bg-muted/40" />
            ))}
            <span className="ml-3 text-xs text-muted">app — live view</span>
          </div>
          <div className="grid gap-4 p-6 sm:grid-cols-3">
            {panels.map((panel) => (
              <div key={panel.label} className="rounded-token bg-background p-5">
                <p className="text-xs uppercase tracking-wider text-muted">{panel.label}</p>
                <p className="mt-2 font-heading text-2xl font-semibold text-accent">
                  {panel.value}
                </p>
                <div className="mt-4 space-y-2" aria-hidden="true">
                  <div className="h-1.5 w-full rounded bg-surface" />
                  <div className="h-1.5 w-4/5 rounded bg-surface" />
                  <div className="h-1.5 w-3/5 rounded bg-surface" />
                </div>
              </div>
            ))}
          </div>
          {caption && (
            <figcaption className="border-t border-background/60 px-6 py-3 text-sm text-muted">
              {caption}
            </figcaption>
          )}
        </figure>
      </Reveal>
    </Section>
  );
}
