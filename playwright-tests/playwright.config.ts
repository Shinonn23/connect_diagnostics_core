import { defineConfig, devices } from '@playwright/test';
import { loadLocalEnv } from './src/lib/env';

loadLocalEnv();

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report/html' }],
  ],

  use: {
    baseURL: process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com',
    storageState: './auth.json',
    ignoreHTTPSErrors: true,
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
      use: { storageState: { cookies: [], origins: [] } },
    },
    {
      name: 'chromium',
      testMatch: /\d{2}-.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: './auth.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'validate',
      testMatch: /(master|stock)-validation\.spec\.ts/,
      use: {
        ignoreHTTPSErrors: true,
      },
    },
    {
      name: 'data-compare',
      testMatch: /master-data-compare\.spec\.ts/,
      use: {
        ignoreHTTPSErrors: true,
      },
    },
  ],
});
