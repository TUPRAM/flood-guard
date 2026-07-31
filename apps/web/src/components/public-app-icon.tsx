export type PublicAppIconName =
  | "camera"
  | "check"
  | "chevron"
  | "close"
  | "drain"
  | "edit"
  | "globe"
  | "hazard"
  | "home"
  | "layers"
  | "locate"
  | "pin"
  | "medical"
  | "menu"
  | "message"
  | "phone"
  | "prepare"
  | "profile"
  | "report"
  | "road"
  | "route"
  | "search"
  | "shelter"
  | "shield"
  | "sos"
  | "water";

interface PublicAppIconProps {
  name: PublicAppIconName;
  className?: string;
}

export function PublicAppIcon({ name, className = "" }: PublicAppIconProps) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  const navbar = { ...common, strokeWidth: 1.8 };

  return (
    <svg
      className={`public-app-icon ${className}`.trim()}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {name === "home" && (
        <>
          <path {...navbar} d="M3.75 10.15 12 3.8l8.25 6.35" />
          <path {...navbar} d="M5.5 9.1v10.4h13V9.1" />
          <path {...navbar} d="M9.6 19.5v-6h4.8v6" />
          <path {...navbar} d="M16.15 6.25V4.7h2.15v3.25" />
        </>
      )}
      {name === "report" && (
        <>
          <path {...navbar} d="M5.4 4.5h13.2A2.4 2.4 0 0 1 21 6.9v8.2a2.4 2.4 0 0 1-2.4 2.4H11l-4.2 2.9v-2.9H5.4A2.4 2.4 0 0 1 3 15.1V6.9a2.4 2.4 0 0 1 2.4-2.4Z" />
          <path {...navbar} d="M12 8v4.1" />
          <circle cx="12" cy="15.2" r=".9" fill="currentColor" />
        </>
      )}
      {name === "shelter" && (
        <>
          <path {...navbar} d="M3.5 9.55 12 3.9l8.5 5.65" />
          <path {...navbar} d="M5 9v9.8M19 9v9.8M4 19.1h16M5 9.55h14" />
          <circle {...navbar} cx="9.35" cy="12.7" r="1.25" />
          <circle {...navbar} cx="14.65" cy="12.7" r="1.25" />
          <path {...navbar} d="M7.15 17.05c.35-1.6 1.1-2.4 2.2-2.4s1.85.8 2.2 2.4" />
          <path {...navbar} d="M12.45 17.05c.35-1.6 1.1-2.4 2.2-2.4s1.85.8 2.2 2.4" />
        </>
      )}
      {name === "prepare" && (
        <>
          <rect {...navbar} x="5" y="5.5" width="14" height="15" rx="2" />
          <path {...navbar} d="M9 5.5V4.4A1.4 1.4 0 0 1 10.4 3h3.2A1.4 1.4 0 0 1 15 4.4v1.1M9 5.5h6" />
          <path {...navbar} d="m8.25 10.45 1.3 1.3 2.15-2.45M13.55 10.55h2.9" />
          <path {...navbar} d="m8.25 15.55 1.3 1.3 2.15-2.45M13.55 15.65h2.9" />
        </>
      )}
      {name === "sos" && (
        <>
          <path {...navbar} d="M7.5 15.55v-4.1a4.5 4.5 0 0 1 9 0v4.1" />
          <path {...navbar} d="M7 15.55h10v3H7zM5.7 18.55h12.6" />
          <path {...navbar} d="M12 2.8v2M5.65 5.3l1.45 1.45M18.35 5.3 16.9 6.75M3.55 11h2M18.45 11h2" />
          <path {...navbar} d="M12 8.1v3.15" />
        </>
      )}
      {name === "menu" && (
        <>
          <path {...common} d="M4 7h16M4 12h16M4 17h16" />
        </>
      )}
      {name === "close" && (
        <>
          <path {...common} d="m6 6 12 12M18 6 6 18" />
        </>
      )}
      {name === "search" && (
        <>
          <circle {...common} cx="10.5" cy="10.5" r="6.5" />
          <path {...common} d="m15.5 15.5 4 4" />
        </>
      )}
      {name === "layers" && (
        <>
          <path {...common} d="m12 3 9 5-9 5-9-5 9-5Z" />
          <path {...common} d="m4.5 12 7.5 4 7.5-4M4.5 16l7.5 4 7.5-4" />
        </>
      )}
      {name === "hazard" && (
        <>
          <circle {...common} cx="12" cy="12" r="9" />
          <path {...common} d="M12 10v6M12 7.2h.01" />
        </>
      )}
      {name === "profile" && (
        <>
          <circle {...common} cx="12" cy="8" r="4" />
          <path {...common} d="M4.5 21c.7-4.2 3.2-6.3 7.5-6.3s6.8 2.1 7.5 6.3" />
        </>
      )}
      {name === "camera" && (
        <>
          <path {...common} d="M4 8.5h3l1.5-2h7l1.5 2h3v10H4v-10Z" />
          <circle {...common} cx="12" cy="13.5" r="3.2" />
        </>
      )}
      {name === "water" && (
        <>
          <path {...common} d="M12 3.5c3.3 4 5 6.8 5 9a5 5 0 0 1-10 0c0-2.2 1.7-5 5-9Z" />
          <path {...common} d="M9.5 13.5c.3 1.4 1.1 2.1 2.5 2.3" />
        </>
      )}
      {name === "road" && (
        <>
          <path {...common} d="M8.5 3 6 21M15.5 3 18 21M12 4.5v3M12 11v3M12 17.5v2" />
        </>
      )}
      {name === "drain" && (
        <>
          <rect {...common} x="4" y="5" width="16" height="14" rx="2" />
          <path {...common} d="M8 8v8M12 8v8M16 8v8" />
        </>
      )}
      {name === "medical" && (
        <>
          <path {...common} d="M9.5 4h5v5h5v5h-5v5h-5v-5h-5V9h5V4Z" />
        </>
      )}
      {name === "route" && (
        <>
          <circle {...common} cx="6" cy="18" r="2" />
          <path {...common} d="M8 18h3a3 3 0 0 0 3-3v-1a3 3 0 0 0-3-3H9a3 3 0 0 1-3-3V6" />
          <circle {...common} cx="6" cy="4" r="2" />
          <path {...common} d="m17 9 3 3-3 3" />
        </>
      )}
      {name === "phone" && (
        <>
          <path {...common} d="M7.2 3.5 10 8l-2.1 2.1a15.7 15.7 0 0 0 6 6L16 14l4.5 2.8-1.2 3.4c-.3.8-1.2 1.3-2.1 1.1C9.7 19.8 4.2 14.3 2.7 6.8c-.2-.9.3-1.8 1.1-2.1l3.4-1.2Z" />
        </>
      )}
      {name === "message" && (
        <>
          <path {...common} d="M4 5h16v11H9l-5 4V5Z" />
          <path {...common} d="M8 9h8M8 12h5" />
        </>
      )}
      {name === "shield" && (
        <>
          <path {...common} d="M12 3.2 19 6v5.4c0 4.3-2.8 7.6-7 9.4-4.2-1.8-7-5.1-7-9.4V6l7-2.8Z" />
          <path {...common} d="m9 12 2.1 2.1L15.2 10" />
        </>
      )}
      {name === "locate" && (
        <>
          <circle {...common} cx="12" cy="12" r="6.4" />
          <circle cx="12" cy="12" r="2.4" fill="currentColor" />
          <path {...common} d="M12 2.2v2.6M12 19.2v2.6M21.8 12h-2.6M4.8 12H2.2" />
        </>
      )}
      {name === "pin" && (
        <>
          <path {...common} d="M12 21c4-4.4 6-7.7 6-10a6 6 0 1 0-12 0c0 2.3 2 5.6 6 10Z" />
          <circle {...common} cx="12" cy="11" r="2.4" />
        </>
      )}
      {name === "globe" && (
        <>
          <circle {...common} cx="12" cy="12" r="8.5" />
          <path {...common} d="M3.5 12h17" />
          <path {...common} d="M12 3.5c2.2 2.4 3.3 5.2 3.3 8.5S14.2 18.1 12 20.5c-2.2-2.4-3.3-5.2-3.3-8.5S9.8 5.9 12 3.5Z" />
        </>
      )}
      {name === "edit" && (
        <>
          <path {...common} d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
          <path {...common} d="m14.5 6.5 3 3" />
        </>
      )}
      {name === "check" && <path {...common} d="m5 12 4 4L19 6" />}
      {name === "chevron" && <path {...common} d="m9 5 7 7-7 7" />}
    </svg>
  );
}
