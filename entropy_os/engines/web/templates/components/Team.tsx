import Reveal from "./Reveal";
import Section from "./Section";

export interface TeamProps {
  eyebrow?: string;
  heading: string;
  sub?: string;
  /** Placeholder roles — swap in real people, photos, and bios. Avatars are
   *  generated initials, never stock or scraped faces. */
  members: { name: string; role: string; bio: string }[];
}

export default function Team({ eyebrow, heading, sub, members }: TeamProps) {
  return (
    <Section eyebrow={eyebrow} heading={heading} sub={sub}>
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {members.map((member, i) => (
          <Reveal key={member.name} delay={i * 60}>
            <article className="h-full rounded-token border border-surface bg-surface p-6">
              <div
                aria-hidden="true"
                className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-background font-heading text-lg font-semibold text-accent"
              >
                {member.name
                  .split(" ")
                  .slice(0, 2)
                  .map((part) => part.charAt(0))
                  .join("")}
              </div>
              <h3 className="font-heading font-semibold text-text">{member.name}</h3>
              <p className="text-sm text-accent">{member.role}</p>
              <p className="mt-3 text-sm leading-relaxed text-muted">{member.bio}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
