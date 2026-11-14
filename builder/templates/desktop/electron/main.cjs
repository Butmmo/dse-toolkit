// Electron shell for __NAME__. It shows the same app you built for the web, in its own window.
const { app, BrowserWindow, Menu, shell, nativeTheme } = require("electron");
const path = require("path");

const DEV_URL = process.env.VITE_DEV_URL;           // set by "npm run desktop:dev"
const single = app.requestSingleInstanceLock();
if (!single) app.quit();

let win;
function create() {
  win = new BrowserWindow({
    width: 1180, height: 780, minWidth: 420, minHeight: 560,
    title: "__NAME__", show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#0f1115" : "#ffffff",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,          // the page cannot reach Node
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.once("ready-to-show", () => win.show());
  if (DEV_URL) win.loadURL(DEV_URL);
  else win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  // Links to other sites open in the normal browser, never inside the app window.
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (/^https?:/.test(url) && !url.startsWith(DEV_URL || "file:")) { e.preventDefault(); shell.openExternal(url); } });
}

app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
app.whenReady().then(() => {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: "File", submenu: [{ role: "quit" }] },
    { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" }] },
    { label: "View", submenu: [{ role: "reload" }, { role: "togglefullscreen" }, { role: "zoomIn" }, { role: "zoomOut" }, { role: "resetZoom" }, ...(DEV_URL ? [{ role: "toggleDevTools" }] : [])] },
  ]));
  create();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) create(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
