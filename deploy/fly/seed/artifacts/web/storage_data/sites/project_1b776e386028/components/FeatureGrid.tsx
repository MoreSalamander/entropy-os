import Reveal from "./Reveal";
import Section from "./Section";

export interface FeatureGridProps {
  eyebrow?: string;
  heading: string;
  sub?: string;
  features: { title: string; description: string }[];
}

const ICONS = [
  "M4 12h16M4 6h16M4 18h10", // lines
  "M12 3v18M3 12h18", // plus
  "M5 13l4 4L19 7", // check
  "M13 3 4 14h6l-1 7 9-11h-6l1-7", // bolt
  "M12 3a9 9 0 1 0 9 9", // arc
  "M4 6h16v12H4zM4 10h16", // panel
];

export default function FeatureGrid({ eyebrow, heading, sub, features }: FeatureGridProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading} sub={sub}>
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature, i) => (
          <Reveal key={feature.title} delay={i * 60}>
            <article className="card-hover h-full rounded-token border border-surface bg-surface p-6">
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-token bg-background">
                <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d={ICONS[i % ICONS.length]} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="text-accent" />
                </svg>
              </div>
              <h3 className="font-heading text-lg font-semibold text-text">{feature.title}</h3>
              <p className="mt-2 leading-relaxed text-muted">{feature.description}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
