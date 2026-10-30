import { defineConfig } from "@playwright/test";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

const root = path.resolve(here, "..");
const py = path.join(root, "backend", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const tmp = path.join(os.tmpdir(), `specloop-e2e-${Date.now()}`);

export default defineConfig({
  testDir: "./e2e",
  timeout: 8 * 60 * 1000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure", viewport: { width: 1600, height: 1000 } },
  webServer: [
    {
      command: `"${py}" -m uvicorn app:app --host 127.0.0.1 --port 8000`,
      cwd: path.join(root, "SpecLoop-Bench", "apis", "bookstore-lab", "sut"),
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 60000,
    },
    {
      command: `"${py}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: path.join(root, "backend"),
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
      env: {
        DATABASE_URL: `sqlite:///${path.join(tmp, "e2e.db").split(path.sep).join("/")}`,
        DATA_DIR: path.join(tmp, "data"),
        TEST_SANDBOX_MAX_RPS: "0",
        LLM_BASE_URL: "",
        LLM_MODEL: "",
      },
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
      env: { VITE_API_TARGET: "http://127.0.0.1:8001" },
    },
  ],
});
