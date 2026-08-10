import Section from "./Section";

export interface FaqProps {
  eyebrow?: string;
  heading: string;
  items: { question: string; answer: string }[];
}

/** Native <details> accordion: keyboard/screen-reader behavior for free. */
export default function Faq({ eyebrow, heading, items }: FaqProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading}>
      <div className="mx-auto max-w-3xl space-y-3">
        {items.map((item) => (
          <details
            key={item.question}
            className="group rounded-token border border-surface bg-surface px-6 py-4"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium text-text [&::-webkit-details-marker]:hidden">
              {item.question}
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                className="shrink-0 transition-transform group-open:rotate-45"
              >
                <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-accent" />
              </svg>
            </summary>
            <p className="mt-3 leading-relaxed text-muted">{item.answer}</p>
          </details>
        ))}
      </div>
    </Section>
  );
}
