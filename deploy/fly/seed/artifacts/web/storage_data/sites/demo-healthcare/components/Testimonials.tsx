import Reveal from "./Reveal";
import Section from "./Section";

export interface TestimonialsProps {
  eyebrow?: string;
  heading: string;
  /** Fictional placeholder personas by design — the generator never
   *  attributes invented quotes to real people or companies. Replace with
   *  real customer quotes before launch. */
  quotes: { quote: string; name: string; role: string }[];
}

export default function Testimonials({ eyebrow, heading, quotes }: TestimonialsProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading}>
      <div className="grid gap-5 md:grid-cols-3">
        {quotes.map((q, i) => (
          <Reveal key={q.name} delay={i * 70}>
            <figure className="card-hover flex h-full flex-col rounded-token border border-surface bg-surface p-6">
              <svg aria-hidden="true" width="24" height="18" viewBox="0 0 24 18" className="mb-4 text-accent">
                <path d="M0 18V9.6C0 3.9 3.4.6 9.2 0l1 2.6C6.6 3.5 5 5.3 4.8 8H10v10H0Zm14 0V9.6C14 3.9 17.4.6 23.2 0l1 2.6c-3.6.9-5.2 2.7-5.4 5.4H24v10H14Z" fill="currentColor" />
              </svg>
              <blockquote className="flex-1 leading-relaxed text-text">{q.quote}</blockquote>
              <figcaption className="mt-5 border-t border-background/60 pt-4">
                <p className="font-medium text-text">{q.name}</p>
                <p className="text-sm text-muted">{q.role}</p>
              </figcaption>
            </figure>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
