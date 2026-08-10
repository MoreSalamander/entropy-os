import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import DocsLayout from "@/components/DocsLayout";
import Hero from "@/components/Hero";
import StatsBand from "@/components/StatsBand";
import Team from "@/components/Team";
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
        <DocsLayout {...c.docs} topics={[...c.docs.topics]} />
        <Team {...c.team} members={[...c.team.members]} />
      </main>
      <Footer {...footer} columns={footer.columns.map((col) => ({ ...col, links: [...col.links] }))} />
    </>
  );
}
