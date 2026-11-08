import type { MetadataRoute } from "next";

/** Installable SignalRankAI app on desktops and phones (owner request, 8 Nov 2026). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SignalRankAI",
    short_name: "SignalRank",
    description: "Multi-asset trading signals with their real record, paper trading and live updates.",
    id: "/app",
    start_url: "/app",
    scope: "/",
    display: "standalone",
    background_color: "#161512",
    theme_color: "#161512",
    categories: ["finance", "productivity"],
    icons: [
      { src: "/brand/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/brand/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/brand/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
