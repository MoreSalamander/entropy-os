import Section from "./Section";

export interface TextBlockProps {
  eyebrow?: string;
  heading: string;
  paragraphs: string[];
}

export default function TextBlock({ eyebrow, heading, paragraphs }: TextBlockProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading}>
      <div className="max-w-3xl space-y-5">
        {paragraphs.map((p, i) => (
          <p key={i} className="text-lg leading-relaxed text-muted">
            {p}
          </p>
        ))}
      </div>
    </Section>
  );
}
