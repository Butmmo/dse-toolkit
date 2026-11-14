import { startDpad } from "./focus";

export function setupPlatform(platform: "web" | "desktop" | "tv") {
  document.documentElement.classList.add(`platform-${platform}`);
  if (platform === "tv") startDpad();
}
