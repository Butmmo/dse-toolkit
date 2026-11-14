import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" lets the same build run from a web host, inside Electron (file://) and on TV runtimes.
export default defineConfig({ base: "./", plugins: [react()] });
