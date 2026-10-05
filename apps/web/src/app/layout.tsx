import type { Metadata, Viewport } from "next";
import "@fontsource-variable/noto-sans-thai/wght.css";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
import "@fontsource-variable/manrope/wght.css";
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "leaflet/dist/leaflet.css";

import { PwaRegister } from "@/components/pwa-register";

import "./globals.css";
import "./public-theme.css";

export const metadata: Metadata = {
  applicationName: "FloodGuard Thailand",
  title: { default: "FloodGuard Thailand", template: "%s · FloodGuard Thailand" },
  description: "Flood preparedness and planning decision support for Mae Sai, Thailand.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/floodguard-logo.png" },
};

/**
 * Pages where the floating app-status pill would cover the page's own map and timeline controls: it hides itself there.
 * This list is written into every built page. The public-production build has no Command page, and its artifact check
 * (scripts/profile-artifact-smoke.mjs) fails on a Command address anywhere in that build, so the profile, which is
 * fixed when the site is built, leaves the exercise page's address out of it.
 */
const AUTO_HIDE_AVAILABILITY_PATHS: readonly string[] = process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE === "public-production"
  ? ["/studio/cases/"]
  : ["/studio/cases/", "/command/exercise/"];

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#073b4c",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main-content">Skip to content</a>{children}<PwaRegister autoHidePaths={AUTO_HIDE_AVAILABILITY_PATHS} /></body></html>;
}
