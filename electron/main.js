const { app, BrowserWindow, dialog, Menu, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");

const PORT = 5000;
const SERVER_URL = `http://127.0.0.1:${PORT}`;
const SERVER_HEALTH = `http://127.0.0.1:${PORT}/health`;

let backendProcess = null;
let mainWindow = null;
let splashWindow = null;

// ── Icon path ──────────────────────────────────────────────────────────────
const ICON_PATH = path.join(__dirname, "assets", "icon.png");

// ── Find the PyInstaller-compiled backend exe ──────────────────────────────
function getBackendPath() {
  if (app.isPackaged) {
    // When packaged by electron-builder, extraResources go to process.resourcesPath
    return path.join(process.resourcesPath, "backend", "ImpanaServer.exe");
  } else {
    // During development (npm start)
    return path.resolve(__dirname, "..", "dist", "ImpanaServer", "ImpanaServer.exe");
  }
}

function getBackendDir() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend");
  } else {
    return path.resolve(__dirname, "..", "dist", "ImpanaServer");
  }
}

// ── Start the Flask backend (PyInstaller compiled exe) ─────────────────────
function startBackend() {
  const exePath = getBackendPath();
  const cwd = getBackendDir();

  backendProcess = spawn(exePath, [], {
    cwd: cwd,
    env: {
      ...process.env,
      FLASK_ENV: "production",
      DATABASE_URL: "postgresql://neondb_owner:npg_2CZtvbkl1gFO@ep-damp-sun-aobcdfmv.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require",
    },
    stdio: "ignore",
    detached: false,
  });

  backendProcess.on("error", (err) => {
    dialog.showErrorBox(
      "Impana Gold — Startup Error",
      "Could not start the billing engine.\n\nPath: " + exePath + "\n\n" + err.message
    );
  });
}

// ── Poll until Flask is ready ──────────────────────────────────────────────
function waitForServer(retries = 60, delayMs = 500) {
  return new Promise((resolve) => {
    const attempt = () => {
      const req = http.get(SERVER_HEALTH, (res) => {
        res.statusCode === 200 ? resolve(true) : retry();
        res.resume();
      });
      req.setTimeout(400);
      req.on("error", retry);
      req.on("timeout", () => { req.destroy(); retry(); });
    };

    const retry = () => {
      if (retries <= 0) { resolve(false); return; }
      retries -= 1;
      setTimeout(attempt, delayMs);
    };

    attempt();
  });
}

// ── Splash / Loading window ────────────────────────────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 300,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    transparent: false,
    backgroundColor: "#0a2540",
    icon: ICON_PATH,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });

  splashWindow.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(`
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * { margin:0; padding:0; box-sizing:border-box; }
      body {
        font-family: 'Segoe UI', Arial, sans-serif;
        background: linear-gradient(135deg, #0a2540 0%, #005f73 100%);
        color: #fff;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        user-select: none;
      }
      .logo-ring {
        width: 80px; height: 80px;
        border-radius: 50%;
        background: rgba(255,255,255,0.12);
        display: flex; align-items: center; justify-content: center;
        margin-bottom: 18px;
        border: 2px solid rgba(255,255,255,0.2);
      }
      .logo-ring img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; }
      h1 { font-size: 26px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; }
      .sub { font-size: 11px; color: rgba(255,255,255,0.65); letter-spacing: 1px; margin-top: 4px; }
      .status { margin-top: 30px; font-size: 12px; color: rgba(255,255,255,0.55); }
      .bar-wrap {
        width: 260px; height: 4px; background: rgba(255,255,255,0.15);
        border-radius: 10px; margin-top: 10px; overflow: hidden;
      }
      .bar {
        height: 100%; width: 0%;
        background: linear-gradient(90deg, #4db8cc, #ffffff);
        border-radius: 10px;
        animation: fill 12s ease-in-out forwards;
      }
      @keyframes fill { 0%{width:0%} 80%{width:85%} 100%{width:95%} }
      .version { position:absolute; bottom:12px; font-size:10px; color:rgba(255,255,255,0.3); }
    </style>
    </head>
    <body>
      <div class="logo-ring">
        <img src="file://${ICON_PATH.replace(/\\/g, '/')}" onerror="this.style.display='none'">
      </div>
      <h1>Impana Gold</h1>
      <div class="sub">M/S SRI DEVI INDUSTRIES</div>
      <div class="status">Starting billing engine, please wait...</div>
      <div class="bar-wrap"><div class="bar"></div></div>
      <div class="version">v1.0.0</div>
    </body>
    </html>
  `));
}

// ── Main application window ────────────────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1366,
    height: 860,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    title: "Impana Gold — Billing System",
    icon: ICON_PATH,
    backgroundColor: "#f5f7fa",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  Menu.setApplicationMenu(null);
  mainWindow.loadURL(SERVER_URL);

  mainWindow.once("ready-to-show", () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.destroy();
    }
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on("closed", () => { mainWindow = null; });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────────
app.setName("Impana Gold");

app.whenReady().then(async () => {
  createSplash();
  startBackend();

  const ready = await waitForServer(60, 500);

  if (!ready) {
    dialog.showErrorBox(
      "Impana Gold — Connection Timeout",
      "The billing engine took too long to start.\n\n" +
      "Please close and reopen the application.\n" +
      "If the problem persists, contact support."
    );
  }

  createMainWindow();
});

app.on("before-quit", () => {
  if (backendProcess) {
    try { backendProcess.kill(); } catch(e) {}
    backendProcess = null;
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});
