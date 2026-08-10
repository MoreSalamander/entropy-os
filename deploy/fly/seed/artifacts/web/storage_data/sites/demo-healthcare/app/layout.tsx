import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://example.com"), // set the real domain at launch
  title: {
    default: "MedMind",
    template: "%s \u2014 MedMind",
  },
  description: "MedMind: Innovative, Compassionate, Expertise-driven Healthcare AI platform.",
  openGraph: {
    title: "MedMind",
    description: "MedMind: Innovative, Compassionate, Expertise-driven Healthcare AI platform.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Playfair+Display:wght@500;600;700&display=swap" />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
