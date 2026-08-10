import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import Cta from "@/components/Cta";
import Hero from "@/components/Hero";
import StatsBand from "@/components/StatsBand";
import { nav, footer, pages } from "@/lib/content";

const c = pages.landing;

export const metadata = {
  title: c.meta.title,
  description: c.meta.description,
};

export default function LandingPage() {
  return (
    <>
      <NavBar {...nav} links={[...nav.links]} />
      <main id="main">
        <Hero {...c.hero} highlights={[...c.hero.highlights]} />
        <StatsBand stats={[...c.stats.stats]} />
        <Cta {...c.cta} />
      </main>
      <Footer {...footer} columns={footer.columns.map((col) => ({ ...col, links: [...col.links] }))} />
    </>
  );
}
