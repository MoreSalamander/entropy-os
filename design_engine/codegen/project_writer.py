"""Phase 6 — the Next.js project writer.

Deterministic assembly: copies the typed component library verbatim, then
GENERATES the parts that vary per project — design tokens (globals.css),
fonts + metadata (layout.tsx), typed content (lib/content.ts), one page.tsx
per PagePlan composing planned sections in order, sitemap/robots, and the
project scaffolding (package.json, tsconfig, next/postcss configs, security
headers). Output is a complete `npx next build`-able repository.

Copy is serialized with json.dumps — a JSON object literal is a valid TS
object literal, so quoting/escaping is handled by the serializer, never by
string surgery.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..models import (DesignSystem, FontClass, GeneratedSite, MotionLevel,
                      PageKind, PagePlan, ProjectIntent, SectionKind)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

# FontClass → (Google Fonts family, css stack suffix, axis spec)
_FONTS: dict[FontClass, tuple[str, str, str]] = {
    FontClass.GEOMETRIC_SANS: ("Poppins", "sans-serif", "wght@400;500;600;700"),
    FontClass.HUMANIST_SANS: ("Inter", "sans-serif", "wght@400;500;600"),
    FontClass.NEO_GROTESQUE: ("Archivo", "sans-serif", "wght@400;500;600;700"),
    FontClass.SERIF_DISPLAY: ("Playfair Display", "serif", "wght@500;600;700"),
    FontClass.MONO_ACCENT: ("JetBrains Mono", "monospace", "wght@400;500"),
}

_PAGE_ROUTES: dict[PageKind, str] = {
    PageKind.LANDING: "app/page.tsx",
    PageKind.PRODUCT: "app/product/page.tsx",
    PageKind.ABOUT: "app/about/page.tsx",
    PageKind.PRICING: "app/pricing/page.tsx",
    PageKind.CONTACT: "app/contact/page.tsx",
    PageKind.DOCS: "app/docs/page.tsx",
}

_PAGE_HREFS: dict[PageKind, str] = {
    PageKind.LANDING: "/", PageKind.PRODUCT: "/product", PageKind.ABOUT: "/about",
    PageKind.PRICING: "/pricing", PageKind.CONTACT: "/contact", PageKind.DOCS: "/docs",
}

# SectionKind → (component name, JSX factory given the page content key)
_MOTION_PARAMS = {MotionLevel.NONE: ("0s", "0px"),
                  MotionLevel.SUBTLE: (".6s", "14px"),
                  MotionLevel.EXPRESSIVE: (".85s", "26px")}


class ProjectWriter:
    def __init__(self, out_dir: Path):
        self.out = out_dir

    # ------------------------------------------------------------------ #
    def write(self, intent: ProjectIntent, ds: DesignSystem,
              page_copy: dict[str, dict]) -> GeneratedSite:
        """page_copy: page kind value -> copywriter dict."""
        if self.out.exists():
            # regeneration keeps node_modules/.next so the build gate and dev
            # loops don't pay a full npm install every iteration
            for child in self.out.iterdir():
                if child.name in ("node_modules",):
                    continue
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        (self.out / "app").mkdir(parents=True, exist_ok=True)
        (self.out / "lib").mkdir(exist_ok=True)
        (self.out / "public").mkdir(exist_ok=True)

        files = 0
        files += self._copy_components(ds)
        files += self._write_scaffolding(intent)
        files += self._write_globals(ds)
        files += self._write_layout(intent, ds)
        files += self._write_content(intent, ds, page_copy)
        for plan in ds.pages:
            files += self._write_page(plan, ds)
        files += self._write_seo(intent, ds)
        return GeneratedSite(project_id="", intent=intent, design_system=ds,
                             out_dir=str(self.out), files_written=files)

    # ------------------------------------------------------------------ #
    def _copy_components(self, ds: DesignSystem) -> int:
        dst = self.out / "components"
        shutil.copytree(TEMPLATES_DIR / "components", dst)
        if ds.motion == MotionLevel.NONE:
            # motion "none": Reveal degrades to a static passthrough so the
            # tree keeps one shape while all animation disappears
            (dst / "Reveal.tsx").write_text(
                'import type { ReactNode } from "react";\n\n'
                "/** Motion level 'none': static passthrough, no observers, no CSS. */\n"
                "export default function Reveal({ children }: { children: ReactNode; delay?: number }) {\n"
                "  return <div>{children}</div>;\n}\n")
        return len(list(dst.glob("*.tsx")))

    def _write_scaffolding(self, intent: ProjectIntent) -> int:
        (self.out / "package.json").write_text(json.dumps({
            "name": intent.product_name.lower().replace(" ", "-")[:40] or "generated-site",
            "private": True,
            "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
            "dependencies": {"next": "^15.1.6", "react": "^19.0.0",
                             "react-dom": "^19.0.0"},
            "devDependencies": {"@tailwindcss/postcss": "^4.0.0",
                                "tailwindcss": "^4.0.0", "typescript": "^5.7.0",
                                "@types/node": "^22.10.0", "@types/react": "^19.0.0",
                                "@types/react-dom": "^19.0.0"},
        }, indent=2) + "\n")
        (self.out / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022", "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": False, "skipLibCheck": True, "strict": True,
                "noEmit": True, "esModuleInterop": True, "module": "esnext",
                "moduleResolution": "bundler", "resolveJsonModule": True,
                "isolatedModules": True, "jsx": "preserve", "incremental": True,
                "plugins": [{"name": "next"}],
                "paths": {"@/*": ["./*"]},
            },
            "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
            "exclude": ["node_modules"],
        }, indent=2) + "\n")
        (self.out / "postcss.config.mjs").write_text(
            'const config = { plugins: { "@tailwindcss/postcss": {} } };\n'
            "export default config;\n")
        (self.out / "next.config.mjs").write_text(
            "/** Security headers on every route — Security Agent baseline. */\n"
            "const securityHeaders = [\n"
            '  { key: "X-Content-Type-Options", value: "nosniff" },\n'
            '  { key: "X-Frame-Options", value: "DENY" },\n'
            '  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },\n'
            '  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },\n'
            "];\n\n"
            "const nextConfig = {\n"
            "  async headers() {\n"
            '    return [{ source: "/(.*)", headers: securityHeaders }];\n'
            "  },\n"
            "};\n\nexport default nextConfig;\n")
        (self.out / ".gitignore").write_text("node_modules/\n.next/\nout/\n")
        return 5

    # ------------------------------------------------------------------ #
    def _write_globals(self, ds: DesignSystem) -> int:
        p = ds.palette
        heading = _FONTS[ds.heading_font]
        body = _FONTS[ds.body_font]
        duration, translate = _MOTION_PARAMS[ds.motion]
        css = f'''@import "tailwindcss";

/* Design tokens — synthesized by design-engine ({ds.id}).
   Palette passed WCAG AA contrast validation (auto-fixed where needed). */
@theme {{
  --color-background: {p.background};
  --color-surface: {p.surface};
  --color-text: {p.text};
  --color-muted: {p.muted};
  --color-accent: {p.accent};
  --font-heading: "{heading[0]}", {heading[1]};
  --font-body: "{body[0]}", {body[1]};
  --font-mono: "JetBrains Mono", monospace;
  --radius-token: {ds.radius_px}px;
}}

body {{
  background: var(--color-background);
  color: var(--color-text);
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
}}

/* Accessible focus treatment everywhere */
:focus-visible {{
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
  border-radius: 4px;
}}

.skip-link {{
  position: absolute;
  left: -9999px;
  top: 0;
  z-index: 100;
  background: var(--color-accent);
  color: var(--color-background);
  padding: 0.6rem 1rem;
  border-radius: 0 0 8px 0;
}}
.skip-link:focus {{ left: 0; }}

/* Scroll reveal (toggled by components/Reveal.tsx) */
.reveal {{
  opacity: 0;
  transform: translateY({translate});
  transition: opacity {duration} ease, transform {duration} ease;
}}
.reveal.is-visible {{ opacity: 1; transform: none; }}

/* Hero/CTA gradient wash keyed to the accent token */
.hero-wash {{
  background-image:
    radial-gradient(60rem 30rem at 85% -10%,
      color-mix(in srgb, var(--color-accent) 14%, transparent), transparent 60%),
    radial-gradient(40rem 24rem at -10% 20%,
      color-mix(in srgb, var(--color-accent) 8%, transparent), transparent 55%);
}}

.card-hover {{ transition: transform {duration} ease, border-color {duration} ease; }}
.card-hover:hover {{ transform: translateY(-3px); border-color: var(--color-muted); }}

/* Motion opt-out wins over everything above */
@media (prefers-reduced-motion: reduce) {{
  .reveal {{ opacity: 1; transform: none; transition: none; }}
  .card-hover, .card-hover:hover {{ transition: none; transform: none; }}
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
}}
'''
        (self.out / "app" / "globals.css").write_text(css)
        return 1

    # ------------------------------------------------------------------ #
    def _write_layout(self, intent: ProjectIntent, ds: DesignSystem) -> int:
        families = []
        for cls in {ds.heading_font, ds.body_font, FontClass.MONO_ACCENT}:
            name, _stack, axes = _FONTS[cls]
            families.append(f"family={name.replace(' ', '+')}:{axes}")
        fonts_url = ("https://fonts.googleapis.com/css2?" + "&".join(sorted(families))
                     + "&display=swap")
        desc = json.dumps(f"{intent.product_name}: "
                          f"{', '.join(intent.brand_position[:3])} "
                          f"{intent.industry} platform.")
        tsx = f'''import type {{ Metadata }} from "next";
import "./globals.css";

export const metadata: Metadata = {{
  metadataBase: new URL("https://example.com"), // set the real domain at launch
  title: {{
    default: {json.dumps(intent.product_name)},
    template: {json.dumps("%s — " + intent.product_name)},
  }},
  description: {desc},
  openGraph: {{
    title: {json.dumps(intent.product_name)},
    description: {desc},
    type: "website",
  }},
}};

export default function RootLayout({{
  children,
}}: Readonly<{{ children: React.ReactNode }}>) {{
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={json.dumps(fonts_url)} />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {{children}}
      </body>
    </html>
  );
}}
'''
        (self.out / "app" / "layout.tsx").write_text(tsx)
        return 1

    # ------------------------------------------------------------------ #
    def _write_content(self, intent: ProjectIntent, ds: DesignSystem,
                       page_copy: dict[str, dict]) -> int:
        hrefs = [_PAGE_HREFS[p.kind] for p in ds.pages]
        # navigation labels are always the canonical short names — page titles
        # may carry flavor, but chrome must stay scannable
        short = {PageKind.LANDING: "Home", PageKind.PRODUCT: "Product",
                 PageKind.ABOUT: "About", PageKind.PRICING: "Pricing",
                 PageKind.CONTACT: "Contact", PageKind.DOCS: "Docs"}
        nav_links = [{"label": short[p.kind], "href": _PAGE_HREFS[p.kind]}
                     for p in ds.pages
                     if p.kind not in (PageKind.LANDING, PageKind.CONTACT)]
        contact_href = "/contact" if "/contact" in hrefs else hrefs[0]
        landing = page_copy.get("landing", {})

        def blocks_for(plan: PagePlan) -> dict:
            c = page_copy.get(plan.kind.value, {})
            cta_href = c.get("_cta_href", contact_href)
            out: dict = {}
            # heading-hierarchy invariant: a page with no h1-bearing section
            # (Hero / DocsLayout) gets a PageHeader injected by _write_page,
            # so its content block must exist
            if not {SectionKind.HERO, SectionKind.DOCS_LAYOUT} & set(plan.sections):
                out["pageHeader"] = {
                    "heading": plan.title,
                    "sub": str(c.get("meta_description") or ""),
                }
            for section in plan.sections:
                if section == SectionKind.HERO:
                    hero = dict(c.get("hero") or {})
                    # every optional field gets a concrete value: `as const`
                    # content must never contain null, and key presence must
                    # be uniform so the page JSX can reference fields safely
                    hero.setdefault("eyebrow", "")
                    hero["highlights"] = list(hero.get("highlights") or [])
                    hero["primaryCta"] = {"label": "Get started", "href": cta_href}
                    if "/product" in hrefs and plan.kind == PageKind.LANDING:
                        hero["secondaryCta"] = {"label": "See the product",
                                                "href": "/product"}
                    out["hero"] = hero
                elif section == SectionKind.LOGO_CLOUD:
                    out["logoCloud"] = {
                        "heading": "Built for teams like these (placeholder logos)",
                        "names": ["Meridian Labs", "Northbeam Health",
                                  "Cobalt Systems", "Halcyon Group", "Vantage Clinical"]}
                elif section == SectionKind.FEATURE_GRID:
                    out["featureGrid"] = {
                        "eyebrow": "Capabilities",
                        "heading": c.get("features_heading",
                                         f"Why {intent.product_name}"),
                        "features": c.get("features", [])}
                elif section == SectionKind.PRODUCT_SHOWCASE:
                    out["showcase"] = {
                        "eyebrow": "Product",
                        "heading": "The work, visible",
                        "sub": "A schematic view — replace with real product imagery.",
                        "panels": list(c.get("showcase_panels") or []),
                        "caption": "Illustrative interface schematic generated by design-engine."}
                elif section == SectionKind.STATS_BAND:
                    out["stats"] = {"stats": c.get("stats", [])}
                elif section == SectionKind.TESTIMONIALS:
                    out["testimonials"] = {
                        "eyebrow": "Voices",
                        "heading": "What early teams say (placeholder personas)",
                        "quotes": c.get("testimonials", [])}
                elif section == SectionKind.PRICING:
                    tiers = []
                    for i, t in enumerate(c.get("pricing_tiers", [])):
                        price = str(t.get("price", ""))
                        period = str(t.get("period") or
                                     ("/mo" if "$" in price and price != "$0" else ""))
                        tiers.append({"name": str(t.get("name", f"Tier {i + 1}")),
                                      "price": price,
                                      "period": period,
                                      "description": str(t.get("description", "")),
                                      "features": [str(f) for f in t.get("features", [])],
                                      "cta": {"label": "Choose " + str(t.get("name", "plan")),
                                              "href": cta_href},
                                      "featured": i == 1})
                    out["pricing"] = {"eyebrow": "Pricing",
                                      "heading": "Simple, honest pricing",
                                      "sub": "Placeholder tiers — align with your real packaging.",
                                      "tiers": tiers}
                elif section == SectionKind.FAQ:
                    out["faq"] = {"eyebrow": "FAQ",
                                  "heading": "Common questions",
                                  "items": c.get("faq", [])}
                elif section == SectionKind.TEAM:
                    out["team"] = {"eyebrow": "Team",
                                   "heading": "The people behind it",
                                   "members": c.get("team", [])}
                elif section == SectionKind.CONTACT_FORM:
                    out["contactForm"] = {"eyebrow": "Contact",
                                          "heading": str(c.get("cta_heading")
                                                         or "Talk to us"),
                                          "sub": str(c.get("cta_sub") or "")}
                elif section == SectionKind.TEXT_BLOCK:
                    out["textBlock"] = {"eyebrow": "About",
                                        "heading": plan.title,
                                        "paragraphs": c.get("paragraphs", [])}
                elif section == SectionKind.DOCS_LAYOUT:
                    topics = c.get("docs_topics", [])
                    out["docs"] = {"heading": "Documentation",
                                   "intro": "Everything needed to evaluate and integrate.",
                                   "topics": [{**t, "id": f"topic-{i}"}
                                              for i, t in enumerate(topics)]}
                elif section == SectionKind.CTA:
                    out["cta"] = {"heading": str(c.get("cta_heading")
                                                 or "Ready when you are"),
                                  "sub": str(c.get("cta_sub") or ""),
                                  "primaryCta": {"label": "Book a walkthrough",
                                                 "href": cta_href}}
            return out

        pages_obj = {p.kind.value: {"meta": {
            "title": page_copy.get(p.kind.value, {}).get("meta_title", p.title),
            "description": page_copy.get(p.kind.value, {}).get("meta_description", ""),
        }, **blocks_for(p)} for p in ds.pages}

        content = {
            "siteConfig": {
                "brand": intent.product_name,
                "tagline": landing.get("meta_description",
                                       f"{intent.industry} platform."),
            },
            "nav": {"brand": intent.product_name, "links": nav_links,
                    "cta": {"label": "Get started", "href": contact_href}},
            "footer": {
                "brand": intent.product_name,
                "tagline": landing.get("meta_description", ""),
                "columns": [
                    {"heading": "Product",
                     "links": [{"label": short[p.kind], "href": _PAGE_HREFS[p.kind]}
                               for p in ds.pages if p.kind != PageKind.LANDING][:4]},
                    {"heading": "Company",
                     "links": ([{"label": "About", "href": "/about"}]
                               if "/about" in hrefs else [])
                     + [{"label": "Contact", "href": contact_href}]},
                    {"heading": "Resources",
                     "links": ([{"label": "Documentation", "href": "/docs"}]
                               if "/docs" in hrefs else [])
                     + [{"label": "Home", "href": "/"}]},
                ],
                "note": "Generated by design-engine — placeholder content is "
                        "labeled and awaits real data.",
            },
            "pages": pages_obj,
        }
        ts = ("// GENERATED by design-engine — typed site content.\n"
              "// Placeholder personas/logos/stats are labeled; replace before launch.\n"
              "/* eslint-disable */\n"
              f"const content = {json.dumps(content, indent=2)} as const;\n\n"
              "export const siteConfig = content.siteConfig;\n"
              "export const nav = content.nav;\n"
              "export const footer = content.footer;\n"
              "export const pages = content.pages;\n"
              "export default content;\n")
        (self.out / "lib" / "content.ts").write_text(ts)
        return 1

    # ------------------------------------------------------------------ #
    _SECTION_RENDER: dict[SectionKind, tuple[str, str]] = {
        # SectionKind -> (component import name, JSX expression using `c`)
        SectionKind.HERO: ("Hero", "<Hero {...c.hero} highlights={[...c.hero.highlights]} />"),
        SectionKind.LOGO_CLOUD: ("LogoCloud", "<LogoCloud {...c.logoCloud} names={[...c.logoCloud.names]} />"),
        SectionKind.FEATURE_GRID: ("FeatureGrid",
                                   "<FeatureGrid {...c.featureGrid} features={[...c.featureGrid.features]} />"),
        SectionKind.PRODUCT_SHOWCASE: ("ProductShowcase",
                                       "<ProductShowcase {...c.showcase} panels={[...c.showcase.panels]} />"),
        SectionKind.STATS_BAND: ("StatsBand", "<StatsBand stats={[...c.stats.stats]} />"),
        SectionKind.TESTIMONIALS: ("Testimonials",
                                   "<Testimonials {...c.testimonials} quotes={[...c.testimonials.quotes]} />"),
        SectionKind.PRICING: ("Pricing",
                              "<Pricing {...c.pricing} tiers={c.pricing.tiers.map((t) => ({ ...t, features: [...t.features] }))} />"),
        SectionKind.FAQ: ("Faq", "<Faq {...c.faq} items={[...c.faq.items]} />"),
        SectionKind.TEAM: ("Team", "<Team {...c.team} members={[...c.team.members]} />"),
        SectionKind.CONTACT_FORM: ("ContactForm", "<ContactForm {...c.contactForm} />"),
        SectionKind.TEXT_BLOCK: ("TextBlock",
                                 "<TextBlock {...c.textBlock} paragraphs={[...c.textBlock.paragraphs]} />"),
        SectionKind.DOCS_LAYOUT: ("DocsLayout",
                                  "<DocsLayout {...c.docs} topics={[...c.docs.topics]} />"),
        SectionKind.CTA: ("Cta", "<Cta {...c.cta} />"),
    }

    def _write_page(self, plan: PagePlan, ds: DesignSystem) -> int:
        route = self.out / _PAGE_ROUTES[plan.kind]
        route.parent.mkdir(parents=True, exist_ok=True)
        body_sections = [s for s in plan.sections
                         if s not in (SectionKind.NAV, SectionKind.FOOTER)]
        needs_header = not {SectionKind.HERO, SectionKind.DOCS_LAYOUT} & set(body_sections)
        imports = sorted({self._SECTION_RENDER[s][0] for s in body_sections
                          if s in self._SECTION_RENDER}
                         | ({"PageHeader"} if needs_header else set()))
        import_lines = ["import NavBar from \"@/components/NavBar\";",
                        "import Footer from \"@/components/Footer\";"]
        import_lines += [f'import {name} from "@/components/{name}";' for name in imports]
        jsx_rows = (["        <PageHeader {...c.pageHeader} />"] if needs_header else [])
        jsx_rows += [f"        {self._SECTION_RENDER[s][1]}"
                     for s in body_sections if s in self._SECTION_RENDER]
        jsx = "\n".join(jsx_rows)
        key = plan.kind.value
        tsx = f'''{chr(10).join(import_lines)}
import {{ nav, footer, pages }} from "@/lib/content";

const c = pages.{key};

export const metadata = {{
  title: c.meta.title,
  description: c.meta.description,
}};

export default function {key.capitalize()}Page() {{
  return (
    <>
      <NavBar {{...nav}} links={{[...nav.links]}} />
      <main id="main">
{jsx}
      </main>
      <Footer {{...footer}} columns={{footer.columns.map((col) => ({{ ...col, links: [...col.links] }}))}} />
    </>
  );
}}
'''
        route.write_text(tsx)
        return 1

    # ------------------------------------------------------------------ #
    def _write_seo(self, intent: ProjectIntent, ds: DesignSystem) -> int:
        hrefs = [_PAGE_HREFS[p.kind] for p in ds.pages]
        (self.out / "app" / "sitemap.ts").write_text(
            'import type { MetadataRoute } from "next";\n\n'
            "export default function sitemap(): MetadataRoute.Sitemap {\n"
            f"  const routes = {json.dumps(hrefs)};\n"
            "  return routes.map((route) => ({\n"
            '    url: `https://example.com${route === "/" ? "" : route}`,\n'
            "    lastModified: new Date(),\n"
            "  }));\n}\n")
        (self.out / "app" / "robots.ts").write_text(
            'import type { MetadataRoute } from "next";\n\n'
            "export default function robots(): MetadataRoute.Robots {\n"
            "  return {\n"
            '    rules: { userAgent: "*", allow: "/" },\n'
            '    sitemap: "https://example.com/sitemap.xml",\n'
            "  };\n}\n")
        return 2
