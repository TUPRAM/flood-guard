"use client";

import Image from "next/image";

import type { Language } from "@/lib/types";
import { LanguageToggle } from "./language-toggle";
import styles from "./workspace-header.module.css";

type Surface = "public" | "planning" | "studio";

export function WorkspaceHeader({ activeSurface, language, onLanguageChange }: {
  activeSurface: Surface;
  language: Language;
  onLanguageChange: (language: Language) => void;
}) {
  const th = language === "th";
  const surfaces = [
    { id: "public", href: "/public/", label: th ? "ประชาชน" : "Public" },
    { id: "planning", href: "/command/", label: th ? "การวางแผน" : "Planning" },
    { id: "studio", href: "/studio/", label: th ? "สตูดิโอ" : "Studio" },
  ];
  const current = surfaces.find(({ id }) => id === activeSurface)!;

  return <header className={styles.header}>
    <a className={styles.brand} href={current.href} aria-label={`FloodGuard ${current.label}`}>
      <Image src="/floodguard-logo.png" alt="" width={38} height={38} priority />
      <span>FloodGuard<small>{activeSurface === "planning" ? th ? "พื้นที่ทำงานวางแผน" : "Planning workspace" : current.label}</small></span>
    </a>
    <nav className={styles.navigation} aria-label={th ? "ส่วนต่าง ๆ ของเว็บไซต์" : "Product surfaces"}>
      {surfaces.map(({ id, href, label }) => <a key={id} href={href} aria-current={id === activeSurface ? "page" : undefined}>{label}</a>)}
    </nav>
    <div className={styles.language}><LanguageToggle language={language} onChange={onLanguageChange} englishLabel="English" /></div>
  </header>;
}
