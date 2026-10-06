"use client";

import Image from "next/image";

import type { Language } from "@/lib/types";
import { LanguageToggle } from "./language-toggle";
import styles from "./workspace-header.module.css";

type Surface = "public" | "planning" | "studio";

export function WorkspaceHeader({ activeSurface, language, onLanguageChange, surfaceRoot = true, hrefFor }: {
  activeSurface: Surface;
  language: Language;
  onLanguageChange: (language: Language) => void;
  /**
   * False on a page that is not the surface's own address, such as an archive page below it. The surface link then
   * leads to a different page, so it marks the section (`aria-current="true"`) instead of naming the current page.
   */
  surfaceRoot?: boolean;
  /**
   * Adds what the page must carry across surfaces (the selected case query) to a surface address. While it returns
   * nothing, before the page has read its own address, the plain address is used.
   */
  hrefFor?: (path: string) => string | undefined;
}) {
  const th = language === "th";
  const surfaces = [
    { id: "public", href: "/public/", label: th ? "ประชาชน" : "Public" },
    { id: "planning", href: "/command/", label: th ? "การวางแผน" : "Planning" },
    { id: "studio", href: "/studio/", label: th ? "สตูดิโอ" : "Studio" },
  ].map((surface) => ({ ...surface, href: hrefFor?.(surface.href) ?? surface.href }));
  const current = surfaces.find(({ id }) => id === activeSurface)!;

  return <header className={styles.header}>
    <a className={styles.brand} href={current.href} aria-label={`FloodGuard ${current.label}`}>
      <Image src="/floodguard-logo.png" alt="" width={38} height={38} priority />
      <span>FloodGuard<small>{activeSurface === "planning" ? th ? "พื้นที่ทำงานวางแผน" : "Planning workspace" : current.label}</small></span>
    </a>
    <nav className={styles.navigation} aria-label={th ? "ส่วนต่าง ๆ ของเว็บไซต์" : "Product surfaces"}>
      {surfaces.map(({ id, href, label }) => <a key={id} href={href} aria-current={id === activeSurface ? (surfaceRoot ? "page" : "true") : undefined}>{label}</a>)}
    </nav>
    <div className={styles.language}><LanguageToggle language={language} onChange={onLanguageChange} englishLabel="English" /></div>
  </header>;
}
