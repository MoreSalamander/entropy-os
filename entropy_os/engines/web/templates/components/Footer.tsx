import Link from "next/link";
import Logo from "./Logo";

export interface FooterProps {
  brand: string;
  tagline: string;
  columns: { heading: string; links: { label: string; href: string }[] }[];
  note?: string;
}

export default function Footer({ brand, tagline, columns, note }: FooterProps) {
  return (
    <footer className="border-t border-surface">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 py-14 md:grid-cols-4">
        <div>
          <p className="flex items-center gap-2.5 font-heading text-lg font-semibold text-text">
            <Logo />
            {brand}
          </p>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">{tagline}</p>
        </div>
        {columns.map((col) => (
          <nav key={col.heading} aria-label={col.heading}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
              {col.heading}
            </h2>
            <ul className="space-y-2">
              {col.links.map((link) => (
                <li key={link.href + link.label}>
                  <Link href={link.href} className="text-sm text-muted transition-colors hover:text-text">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-surface/60">
        <p className="mx-auto max-w-6xl px-5 py-5 text-xs text-muted">
          © {new Date().getFullYear()} {brand}. {note ?? "All rights reserved."}
        </p>
      </div>
    </footer>
  );
}
