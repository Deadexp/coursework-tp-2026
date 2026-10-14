import { defineConfig, devices } from '@playwright/test'

// E2E-тесты идут против запущенной системы: сначала `docker compose up -d`.
export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
