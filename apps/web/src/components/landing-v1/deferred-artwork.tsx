/* eslint-disable @next/next/no-img-element -- preoptimized static artwork; native noscript fallback and stricter viewport loading. */
"use client";

import { useEffect, useRef, useState, type ImgHTMLAttributes } from "react";

type Props = ImgHTMLAttributes<HTMLImageElement> & { eager?: boolean };

/** Native lazy loading can fetch several scenes ahead. Keep later plates out of the initial request set. */
export function DeferredArtwork({ eager = false, src, srcSet, alt = "", ...props }: Props) {
  const image = useRef<HTMLImageElement>(null);
  const [nearby, setNearby] = useState(eager);
  useEffect(() => {
    if (nearby || !image.current) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setNearby(true);
        observer.disconnect();
      }
    }, { rootMargin: "0px" });
    observer.observe(image.current);
    return () => observer.disconnect();
  }, [nearby]);
  return <>
    <img {...props} ref={image} src={nearby ? src : undefined} srcSet={nearby ? srcSet : undefined} alt={alt} loading={eager ? "eager" : "lazy"} />
    {!eager && <noscript><img {...props} src={src} srcSet={srcSet} alt={alt} loading="lazy" /></noscript>}
  </>;
}
