export interface DocsLayoutProps {
  heading: string;
  intro: string;
  topics: { id: string; title: string; body: string; code?: string }[];
}

/** Documentation page: sticky topic sidebar + anchored articles. Server
 *  component; in-page navigation is plain anchors, so it works with JS off. */
export default function DocsLayout({ heading, intro, topics }: DocsLayoutProps) {
  return (
    <section className="mx-auto grid max-w-6xl gap-10 px-5 py-16 lg:grid-cols-[220px_1fr]">
      <nav aria-label="Documentation topics" className="lg:sticky lg:top-24 lg:self-start">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
          On this page
        </h2>
        <ul className="space-y-1.5 border-l border-surface">
          {topics.map((topic) => (
            <li key={topic.id}>
              <a
                href={`#${topic.id}`}
                className="block border-l-2 border-transparent py-1 pl-4 text-sm text-muted transition-colors hover:border-accent hover:text-text"
              >
                {topic.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div>
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-text">{heading}</h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">{intro}</p>
        <div className="mt-12 space-y-14">
          {topics.map((topic) => (
            <article key={topic.id} id={topic.id} className="scroll-mt-24">
              <h2 className="font-heading text-2xl font-semibold text-text">{topic.title}</h2>
              <p className="mt-3 leading-relaxed text-muted">{topic.body}</p>
              {topic.code && (
                <pre className="mt-4 overflow-x-auto rounded-token border border-surface bg-surface p-4 text-sm text-text">
                  <code style={{ fontFamily: "var(--font-mono)" }}>{topic.code}</code>
                </pre>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
