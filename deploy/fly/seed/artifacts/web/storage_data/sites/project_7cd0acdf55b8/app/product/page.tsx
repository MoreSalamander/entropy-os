import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import Cta from "@/components/Cta";
import DocsLayout from "@/components/DocsLayout";
import Hero from "@/components/Hero";
import ProductShowcase from "@/components/ProductShowcase";
import StatsBand from "@/components/StatsBand";
import { nav, footer, pages } from "@/lib/content";

const c = pages.product;

export const metadata = {
  title: c.meta.title,
  description: c.meta.description,
};

export default function ProductPage() {
  return (
    <>
      <NavBar {...nav} links={[...nav.links]} />
      <main id="main">
        <Hero {...c.hero} highlights={[...c.hero.highlights]} />
        <StatsBand stats={[...c.stats.stats]} />
        <ProductShowcase {...c.showcase} panels={[...c.showcase.panels]} />
        <DocsLayout {...c.docs} topics={[...c.docs.topics]} />
        <Cta {...c.cta} />
      </main>
      <Footer {...footer} columns={footer.columns.map((col) => ({ ...col, links: [...col.links] }))} />
    </>
  );
}
