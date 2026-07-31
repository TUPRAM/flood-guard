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

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#073b4c",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="th"><body><a className="skip-link" href="#main-content">Skip to content</a>{children}<PwaRegister /></body></html>;
}
