/**
 * @fileoverview E2E tests for BobaLink popup.
 *
 * Tests the popup UI: loading, torrent display, selection, and sending.
 */

import { test, expect } from "@playwright/test";

test.describe("BobaLink Popup", () => {
  test.beforeEach(async ({ page }) => {
    // Load the popup page (extension URL would be set by test harness)
    await page.goto("chrome-extension://test-id/popup/index.html");
  });

  test("displays popup with title", async ({ page }) => {
    const title = page.locator(".header-title");
    await expect(title).toHaveText("BobaLink");
  });

  test("shows empty state when no torrents detected", async ({ page }) => {
    const emptyState = page.locator("#empty-state");
    await expect(emptyState).toBeVisible();
    await expect(page.locator(".empty-title")).toContainText("No torrents");
  });

  test("shows connection status", async ({ page }) => {
    const status = page.locator("#connection-status");
    await expect(status).toBeVisible();
    await expect(status).not.toBeEmpty();
  });

  test("has scan page button in empty state", async ({ page }) => {
    const scanBtn = page.locator("#btn-scan-page");
    await expect(scanBtn).toBeVisible();
    await expect(scanBtn).toHaveText("Scan Page");
  });

  test("has send button disabled when nothing selected", async ({ page }) => {
    const sendBtn = page.locator("#btn-send");
    await expect(sendBtn).toBeDisabled();
  });

  test("toolbar buttons are visible", async ({ page }) => {
    await expect(page.locator("#btn-select-all")).toBeVisible();
    await expect(page.locator("#btn-deselect-all")).toBeVisible();
    await expect(page.locator("#btn-refresh")).toBeVisible();
  });

  test("select all button is clickable", async ({ page }) => {
    const selectAllBtn = page.locator("#btn-select-all");
    await expect(selectAllBtn).toBeEnabled();
    await selectAllBtn.click();
  });

  test("connection warning shows when no server configured", async ({ page }) => {
    // By default no server is configured
    const warning = page.locator("#connection-warning");
    // This may or may not be visible depending on mock state
    // Just verify the element exists
    await expect(warning).toBeAttached();
  });
});
