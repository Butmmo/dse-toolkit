import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import spec from "./spec.json";
import type { Spec } from "./types";
import { setupPlatform } from "./platform";
import "./index.css";
import "./tv.css";

const s = spec as Spec;
setupPlatform(s.platform);
createRoot(document.getElementById("root")!).render(<StrictMode><App spec={s} /></StrictMode>);

// Offline shell for the browser build (skipped inside Electron and on TV runtimes).
if ("serviceWorker" in navigator && s.platform === "web" && location.protocol.startsWith("http")) {
  navigator.serviceWorker.register("./sw.js").catch(() => undefined);
}
