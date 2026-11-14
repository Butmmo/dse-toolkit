// The only things the page may ask the desktop shell. Add safe, specific functions here (never expose Node itself).
const { contextBridge } = require("electron");
contextBridge.exposeInMainWorld("desktop", { platform: process.platform, version: process.versions.electron });
