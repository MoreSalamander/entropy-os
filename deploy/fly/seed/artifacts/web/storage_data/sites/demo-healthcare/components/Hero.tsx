import Link from "next/link";
import Reveal from "./Reveal";

export interface HeroProps {
  eyebrow?: string;
  headline: string;
  subheadline: string;
  primaryCta: { label: string; href: string };
  secondaryCta?: { label: string; href: string };
  highlights?: string[];
}

/** Animated hero: staged reveal, gradient wash keyed to the accent token,
 *  primary + secondary CTA, optional proof highlights under the fold line. */
export default function Hero({
  eyebrow,
  headline,
  subheadline,
  primaryCta,
  secondaryCta,
  highlights = [],
}: HeroProps) {
  return (
    <section className="hero-wash relative overflow-hidden">
      <div className="mx-auto max-w-6xl px-5 pb-20 pt-24 md:pb-28 md:pt-36">
        <div className="max-w-3xl">
          <Reveal>
            {eyebrow && (
              <p className="mb-5 inline-block rounded-full border border-surface bg-surface px-3.5 py-1.5 text-sm text-muted">
                {eyebrow}
              </p>
            )}
          </Reveal>
          <Reveal delay={80}>
            <h1 className="font-heading text-4xl font-semibold leading-[1.08] tracking-tight text-text md:text-6xl">
              {headline}
            </h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted md:text-xl">
              {subheadline}
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href={primaryCta.href}
                className="rounded-token bg-accent px-6 py-3 font-medium text-background transition-transform hover:-translate-y-0.5"
              >
                {primaryCta.label}
              </Link>
              {secondaryCta && (
                <Link
                  href={secondaryCta.href}
                  className="rounded-token border border-surface px-6 py-3 font-medium text-text transition-colors hover:border-muted"
                >
                  {secondaryCta.label}
                </Link>
              )}
            </div>
          </Reveal>
          {highlights.length > 0 && (
            <Reveal delay={320}>
              <ul className="mt-10 flex flex-wrap gap-x-7 gap-y-2">
                {highlights.map((h) => (
                  <li key={h} className="flex items-center gap-2 text-sm text-muted">
                    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M2.5 7.5 5.5 10.5 11.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-accent" />
                    </svg>
                    {h}
                  </li>
                ))}
              </ul>
            </Reveal>
          )}
        </div>
      </div>
    </section>
  );
}
