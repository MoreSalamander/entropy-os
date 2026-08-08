import Link from "next/link";
import Reveal from "./Reveal";
import Section from "./Section";

export interface PricingProps {
  eyebrow?: string;
  heading: string;
  sub?: string;
  tiers: {
    name: string;
    price: string;
    period?: string;
    description: string;
    features: string[];
    cta: { label: string; href: string };
    featured?: boolean;
  }[];
}

export default function Pricing({ eyebrow, heading, sub, tiers }: PricingProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading} sub={sub}>
      <div className="grid items-stretch gap-5 md:grid-cols-3">
        {tiers.map((tier, i) => (
          <Reveal key={tier.name} delay={i * 70}>
            <article
              className={`flex h-full flex-col rounded-token border p-7 ${
                tier.featured
                  ? "border-accent bg-surface shadow-2xl"
                  : "border-surface bg-surface/60"
              }`}
            >
              {tier.featured && (
                <p className="mb-3 w-fit rounded-full bg-accent px-3 py-1 text-xs font-medium text-background">
                  Most popular
                </p>
              )}
              <h3 className="font-heading text-lg font-semibold text-text">{tier.name}</h3>
              <p className="mt-3">
                <span className="font-heading text-4xl font-semibold text-text">{tier.price}</span>
                {tier.period && <span className="ml-1 text-sm text-muted">{tier.period}</span>}
              </p>
              <p className="mt-3 text-sm leading-relaxed text-muted">{tier.description}</p>
              <ul className="mt-6 flex-1 space-y-2.5">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-text">
                    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" className="mt-0.5 shrink-0">
                      <path d="M2.5 7.5 5.5 10.5 11.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-accent" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                href={tier.cta.href}
                className={`mt-7 rounded-token px-5 py-2.5 text-center font-medium transition-opacity hover:opacity-90 ${
                  tier.featured
                    ? "bg-accent text-background"
                    : "border border-surface text-text"
                }`}
              >
                {tier.cta.label}
              </Link>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
