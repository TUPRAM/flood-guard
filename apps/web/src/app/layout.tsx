import type { Metadata, Viewport } from "next";
import "leaflet/dist/leaflet.css";

import { PwaRegister } from "@/components/pwa-register";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FloodGuard Thailand", template: "%s · FloodGuard Thailand" },
  description: "Non-operational flood preparedness and planning decision-support demonstration.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#073b4c",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="th"><body><a className="skip-link" href="#main-content">Skip to content</a>{children}<PwaRegister /></body></html>;
}
