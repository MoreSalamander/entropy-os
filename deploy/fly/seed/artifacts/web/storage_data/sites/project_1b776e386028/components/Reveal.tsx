"use client";

/**
 * Scroll-reveal wrapper. CSS drives the animation (see globals.css); this
 * component only toggles `is-visible` via IntersectionObserver, so motion
 * cost is one class flip. `prefers-reduced-motion` disables the whole
 * effect at the CSS layer — users who opt out never see movement.
 */
import { useEffect, useRef, type ReactNode } from "react";

export default function Reveal({
  children,
  delay = 0,
}: {
  children: ReactNode;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add("is-visible");
            observer.disconnect();
          }
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="reveal" style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}
