import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import Cta from "@/components/Cta";
import Hero from "@/components/Hero";
import Pricing from "@/components/Pricing";
import StatsBand from "@/components/StatsBand";
import { nav, footer, pages } from "@/lib/content";

const c = pages.pricing;

export const metadata = {
  title: c.meta.title,
  description: c.meta.description,
};

export default function PricingPage() {
  return (
    <>
      <NavBar {...nav} links={[...nav.links]} />
      <main id="main">
        <Hero {...c.hero} highlights={[...c.hero.highlights]} />
        <StatsBand stats={[...c.stats.stats]} />
        <Pricing {...c.pricing} tiers={c.pricing.tiers.map((t) => ({ ...t, features: [...t.features] }))} />
        <Cta {...c.cta} />
      </main>
      <Footer {...footer} columns={footer.columns.map((col) => ({ ...col, links: [...col.links] }))} />
    </>
  );
}
