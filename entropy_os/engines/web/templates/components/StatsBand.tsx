import Reveal from "./Reveal";

export interface StatsBandProps {
  /** Illustrative figures — clearly placeholder until real metrics exist. */
  stats: { value: string; label: string }[];
}

export default function StatsBand({ stats }: StatsBandProps) {
  return (
    <section className="border-y border-surface bg-surface/50">
      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-14 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat, i) => (
          <Reveal key={stat.label} delay={i * 60}>
            <div>
              <p className="font-heading text-4xl font-semibold text-text">{stat.value}</p>
              <p className="mt-1.5 text-sm text-muted">{stat.label}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
