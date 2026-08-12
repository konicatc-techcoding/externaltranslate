import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

/**
 * Overlay checks that a jsdom test cannot make: real layout boxes and real
 * animations. Deliberately no pixel snapshots — they fail on a font update
 * and say nothing about why.
 *
 * The page is the production build served by `vite preview`, and the caption
 * socket is stubbed in the page, so nothing here needs a backend, an API key
 * or a microphone.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // `--host` is required: vite binds localhost (IPv6 ::1) by default, and
    // the readiness check below dials 127.0.0.1.
    command: `npm run preview -- --port ${PORT} --strictPort --host 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
