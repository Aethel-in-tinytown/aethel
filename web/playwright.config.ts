/** Browser flows run against an isolated, offline organism and real API. */
import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:8765", trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1050 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command: `${process.env.AETHEL_E2E_PYTHON ?? "python3"} ../aethel_live.py --serve --offline --port 8765 --ws-port 8766 --time-scale 60 --language-backend ${process.env.AETHEL_E2E_LANGUAGE ?? "heuristic"} --http-engine ${process.env.AETHEL_E2E_HTTP ?? "stdlib"} --ws-engine ${process.env.AETHEL_E2E_WS ?? "none"}`,
    env: {
      AETHEL_HOME: `/tmp/aethel-e2e-${Date.now()}`,
      AETHEL_OWNER_TOKEN: "test-owner-token",
      PYTHONHASHSEED: "0",
    },
    url: "http://127.0.0.1:8765/health/ready",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
