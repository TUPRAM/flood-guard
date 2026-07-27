"use client";

import { useEffect, useRef, useState } from "react";

import { LanguageToggle } from "@/components/language-toggle";
import type { Language } from "@/lib/types";

import { PublicAppIcon } from "./public-app-icon";

interface PublicAppHeaderProps {
  language: Language;
  onLanguageChange: (language: Language) => void;
  planningAreaName: string;
  needsSummary: string;
  onNavigatePrepare: () => void;
  onNavigateSos: () => void;
}

export function PublicAppHeader({
  language,
  onLanguageChange,
  planningAreaName,
  needsSummary,
  onNavigatePrepare,
  onNavigateSos,
}: PublicAppHeaderProps) {
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const th = language === "th";

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        menuButtonRef.current?.focus();
      }
      if (event.key !== "Tab" || !drawerRef.current) return;

      const focusable = [...drawerRef.current.querySelectorAll<HTMLElement>(
        "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      )].filter((element) => !element.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const focusTimer = window.setTimeout(
      () => drawerRef.current?.querySelector<HTMLElement>("button")?.focus(),
      0,
    );
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const closeAndNavigate = (navigate: () => void) => {
    setOpen(false);
    navigate();
  };

  return (
    <>
      <header className="public-app-header">
        <button
          ref={menuButtonRef}
          type="button"
          className="public-profile-trigger"
          aria-label={th ? "เปิดโปรไฟล์ครัวเรือน" : "Open household profile"}
          aria-expanded={open}
          aria-controls="public-profile-drawer"
          onClick={() => setOpen(true)}
        >
          <PublicAppIcon name="menu" />
        </button>
        <a href="/public/" className="public-wordmark" aria-label="FloodGuard home">
          FloodGuard
        </a>
        <LanguageToggle language={language} onChange={onLanguageChange} />
      </header>

      {open && (
        <div
          className="public-profile-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) {
              setOpen(false);
              menuButtonRef.current?.focus();
            }
          }}
        >
          <aside
            ref={drawerRef}
            id="public-profile-drawer"
            className="public-profile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={th ? "โปรไฟล์ครัวเรือน" : "Household profile"}
          >
            <div className="public-profile-drawer-heading">
              <div className="public-profile-avatar" aria-hidden="true">
                <PublicAppIcon name="profile" />
              </div>
              <div>
                <p>{th ? "โปรไฟล์ครัวเรือน" : "Household profile"}</p>
                <h2>{th ? "ครัวเรือนของฉัน" : "My household"}</h2>
              </div>
              <button
                type="button"
                className="public-icon-button"
                aria-label={th ? "ปิดโปรไฟล์" : "Close profile"}
                onClick={() => {
                  setOpen(false);
                  menuButtonRef.current?.focus();
                }}
              >
                <PublicAppIcon name="close" />
              </button>
            </div>

            <dl className="public-profile-summary">
              <div>
                <dt>{th ? "พื้นที่วางแผน" : "Planning area"}</dt>
                <dd>{planningAreaName || (th ? "เลือกจากหน้าแรก" : "Choose from Home")}</dd>
              </div>
              <div>
                <dt>{th ? "ความต้องการในครัวเรือน" : "Household needs"}</dt>
                <dd>{needsSummary}</dd>
              </div>
            </dl>

            <p className="public-profile-privacy">
              {th
                ? "โปรไฟล์นี้ใช้ชื่อครัวเรือนทั่วไปและเก็บแผนไว้ในอุปกรณ์นี้"
                : "This profile uses a general household label and keeps the plan on this device."}
            </p>

            <div className="public-profile-actions">
              <button type="button" onClick={() => closeAndNavigate(onNavigatePrepare)}>
                <PublicAppIcon name="prepare" />
                <span>{th ? "แก้ไขความต้องการในครัวเรือน" : "Edit household needs"}</span>
                <PublicAppIcon name="chevron" />
              </button>
              <button type="button" className="danger" onClick={() => closeAndNavigate(onNavigateSos)}>
                <PublicAppIcon name="sos" />
                <span>{th ? "หมายเลขฉุกเฉิน" : "Emergency numbers"}</span>
                <PublicAppIcon name="chevron" />
              </button>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
