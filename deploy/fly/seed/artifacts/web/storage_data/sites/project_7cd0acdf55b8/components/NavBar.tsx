import Link from "next/link";
import Logo from "./Logo";

export interface NavBarProps {
  brand: string;
  links: { label: string; href: string }[];
  cta: { label: string; href: string };
}

/**
 * Sticky top navigation. Server component; the mobile menu is a native
 * <details> disclosure — keyboard- and screen-reader-usable with zero JS.
 */
export default function NavBar({ brand, links, cta }: NavBarProps) {
  return (
    <header className="sticky top-0 z-50 border-b border-surface bg-background/85 backdrop-blur">
      <nav
        aria-label="Main"
        className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5"
      >
        <Link href="/" className="flex items-center gap-2.5 font-heading text-lg font-semibold text-text">
          <Logo />
          {brand}
        </Link>

        <ul className="hidden items-center gap-7 md:flex">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="text-sm text-muted transition-colors hover:text-text focus-visible:text-text"
              >
                {link.label}
              </Link>
            </li>
          ))}
          <li>
            <Link
              href={cta.href}
              className="rounded-token bg-accent px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              {cta.label}
            </Link>
          </li>
        </ul>

        <details className="relative md:hidden">
          <summary
            aria-label="Open menu"
            className="flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-token text-text [&::-webkit-details-marker]:hidden"
          >
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </summary>
          <ul className="absolute right-0 mt-2 w-52 rounded-token border border-surface bg-surface p-2 shadow-xl">
            {links.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="block rounded px-3 py-2 text-sm text-text hover:bg-background">
                  {link.label}
                </Link>
              </li>
            ))}
            <li className="mt-1 border-t border-background pt-1">
              <Link href={cta.href} className="block rounded px-3 py-2 text-sm font-medium text-accent">
                {cta.label}
              </Link>
            </li>
          </ul>
        </details>
      </nav>
    </header>
  );
}
