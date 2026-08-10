import { siteConfig } from "@/lib/content";

/** Generated brand mark: the product initial in a rounded tile. Pure SVG —
 *  no raster assets anywhere in the generated site by design. */
export default function Logo() {
  const initial = siteConfig.brand.charAt(0).toUpperCase();
  return (
    <svg
      aria-hidden="true"
      width="28"
      height="28"
      viewBox="0 0 28 28"
      className="shrink-0"
    >
      <rect width="28" height="28" rx="7" className="fill-accent" />
      <text
        x="14"
        y="19"
        textAnchor="middle"
        fontSize="15"
        fontWeight="700"
        className="fill-background"
        style={{ fontFamily: "var(--font-heading)" }}
      >
        {initial}
      </text>
    </svg>
  );
}
