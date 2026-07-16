"use client";

import type { Language } from "@/lib/types";

export function LanguageToggle({ language, onChange }: { language: Language; onChange: (value: Language) => void }) {
  return (
    <div className="language-toggle" role="group" aria-label="Language / ภาษา">
      <button className={language === "th" ? "active" : ""} onClick={() => onChange("th")} type="button" lang="th">
        ไทย
      </button>
      <button className={language === "en" ? "active" : ""} onClick={() => onChange("en")} type="button" lang="en">
        EN
      </button>
    </div>
  );
}
