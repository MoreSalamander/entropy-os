import Link from "next/link";
import Reveal from "./Reveal";

export interface CtaProps {
  heading: string;
  sub?: string;
  primaryCta: { label: string; href: string };
  secondaryCta?: { label: string; href: string };
}

export default function Cta({ heading, sub, primaryCta, secondaryCta }: CtaProps) {
  return (
    <section className="py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <Reveal>
          <div className="hero-wash overflow-hidden rounded-token border border-surface bg-surface px-8 py-14 text-center md:py-20">
            <h2 className="mx-auto max-w-2xl font-heading text-3xl font-semibold tracking-tight text-text md:text-4xl">
              {heading}
            </h2>
            {sub && <p className="mx-auto mt-4 max-w-xl text-lg text-muted">{sub}</p>}
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <Link
                href={primaryCta.href}
                className="rounded-token bg-accent px-6 py-3 font-medium text-background transition-transform hover:-translate-y-0.5"
              >
                {primaryCta.label}
              </Link>
              {secondaryCta && (
                <Link
                  href={secondaryCta.href}
                  className="rounded-token border border-background/40 px-6 py-3 font-medium text-text transition-colors hover:border-muted"
                >
                  {secondaryCta.label}
                </Link>
              )}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
