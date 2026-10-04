"use client";

import { ArrowUpRight, Menu, Waves } from "lucide-react";
import { useEffect, useRef } from "react";
import styles from "./landing.module.css";

const workspaces = [["Public", "/public/"], ["Planning", "/command/"], ["Studio", "/studio/"]] as const;

// Workspace links use document navigation, matching the workspaces' native Back history.

export function LandingNavigation() {
  const menu = useRef<HTMLDetailsElement>(null);
  const workspaceMenu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const html = document.documentElement;
    const desktop = window.matchMedia("(min-width: 1100px) and (min-height: 700px)");
    let idleTimer = 0;
    let nearScrollbar = false;
    const hide = () => { html.dataset.landingScrolling = "false"; };
    const show = () => {
      if (!desktop.matches) return;
      window.clearTimeout(idleTimer);
      html.dataset.landingScrolling = "true";
      if (!nearScrollbar) idleTimer = window.setTimeout(hide, 900);
    };
    const onPointer = (event: PointerEvent) => {
      const near = event.clientX >= html.clientWidth - 14;
      if (near === nearScrollbar) return;
      nearScrollbar = near;
      show();
    };
    const onLeave = () => { nearScrollbar = false; show(); };
    const onResize = () => {
      nearScrollbar = false;
      window.clearTimeout(idleTimer);
      delete html.dataset.landingScrolling;
      show();
    };
    window.addEventListener("scroll", show, { passive: true });
    window.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    desktop.addEventListener("change", onResize);
    show();
    return () => {
      window.clearTimeout(idleTimer);
      window.removeEventListener("scroll", show);
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("pointerleave", onLeave);
      desktop.removeEventListener("change", onResize);
      delete html.dataset.landingScrolling;
    };
  }, []);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        for (const entry of [menu.current, workspaceMenu.current]) {
          if (!entry?.open) continue;
          entry.open = false;
          entry.querySelector("summary")?.focus();
        }
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  return <header className={styles.header}>
    <a className={styles.brand} href="#hero" aria-label="FloodGuard home"><span className={styles.publicBrandMark} data-landing-brand-mark aria-hidden="true" /><Waves size={28} strokeWidth={1.7} /><span>FloodGuard<span className={styles.brandDot}>.</span></span></a>
    <nav className={styles.desktopNav} aria-label="Landing navigation">
      <a href="#place">The story</a><a href="#method">How it works</a><a href="#inputs">Data</a><a href="#pipeline">Pipeline</a>
      <details ref={workspaceMenu} className={styles.workspaceMenu}><summary>Workspaces</summary><div>{workspaces.map(([label, href]) => <a key={href} href={href}>{label}<ArrowUpRight size={16} /></a>)}</div></details>
      <a href="#case">Evidence</a>
    </nav>
    <div className={styles.headerActions}><span className={styles.language} lang="en">EN</span><a className={styles.demoButton} href="/command/"><span className={styles.desktopDemo}>Planning demo</span><span className={styles.mobileDemo}>Demo</span><ArrowUpRight size={17} /></a></div>
    <details ref={menu} className={styles.mobileMenu}><summary aria-label="Open navigation menu"><Menu size={24} /></summary>
      <nav aria-label="Mobile navigation" onClick={(event) => { if ((event.target as Element).closest("a") && menu.current) menu.current.open = false; }}>
        <a href="#place">The story</a><a href="#method">How it works</a><a href="#inputs">Data</a><a href="#pipeline">Pipeline</a><a href="#workspaces">Workspaces</a><a href="#case">Evidence</a>
        {workspaces.map(([label, href]) => <a key={href} href={href}>Open {label}<ArrowUpRight size={18} /></a>)}<span>English</span>
      </nav>
    </details>
  </header>;
}
