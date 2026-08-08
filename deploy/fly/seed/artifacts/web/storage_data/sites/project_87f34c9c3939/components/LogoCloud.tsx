import Section from "./Section";

export interface LogoCloudProps {
  heading: string;
  /** Placeholder organization names — the generator NEVER emits real brand
   *  names as fake customers; replace with real customers before launch. */
  names: string[];
}

export default function LogoCloud({ heading, names }: LogoCloudProps) {
  return (
    <Section tight>
      <p className="mb-8 text-center text-sm uppercase tracking-widest text-muted">
        {heading}
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-x-12 gap-y-5">
        {names.map((name) => (
          <li
            key={name}
            className="font-heading text-lg font-semibold tracking-wide text-muted/70"
          >
            {name}
          </li>
        ))}
      </ul>
    </Section>
  );
}
