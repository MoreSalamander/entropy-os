import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import Hero from "@/components/Hero";
import { nav, footer, pages } from "@/lib/content";

const c = pages.contact;

export const metadata = {
  title: c.meta.title,
  description: c.meta.description,
};

export default function ContactPage() {
  return (
    <>
      <NavBar {...nav} links={[...nav.links]} />
      <main id="main">
        <Hero {...c.hero} highlights={[...c.hero.highlights]} />
      </main>
      <Footer {...footer} columns={footer.columns.map((col) => ({ ...col, links: [...col.links] }))} />
    </>
  );
}
