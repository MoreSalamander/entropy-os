import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = ["/", "/product", "/about", "/pricing"];
  return routes.map((route) => ({
    url: `https://example.com${route === "/" ? "" : route}`,
    lastModified: new Date(),
  }));
}
