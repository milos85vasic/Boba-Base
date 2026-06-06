/**
 * @fileoverview E2E tests for BobaLink options page.
 *
 * Tests the options page: navigation, form inputs, server management.
 */

import { test, expect } from "@playwright/test";

test.describe("BobaLink Options", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("chrome-extension://test-id/options/index.html");
  });

  test("loads options page with sidebar", async ({ page }) => {
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(page.locator(".sidebar-brand h1")).toHaveText("BobaLink");
  });

  test("has navigation items", async ({ page }) => {
    const navItems = page.locator(".nav-item");
    await expect(navItems).toHaveCount(4);
    await expect(navItems.nth(0)).toContainText("Servers");
    await expect(navItems.nth(1)).toContainText("General");
    await expect(navItems.nth(2)).toContainText("Advanced");
    await expect(navItems.nth(3)).toContainText("About");
  });

  test("servers section is active by default", async ({ page }) => {
    await expect(page.locator("#section-servers")).toHaveClass(/active/);
  });

  test("can navigate to General section", async ({ page }) => {
    await page.locator(".nav-item[data-section='general']").click();
    await expect(page.locator("#section-general")).toHaveClass(/active/);
    await expect(page.locator("#section-servers")).not.toHaveClass(/active/);
  });

  test("can navigate to Advanced section", async ({ page }) => {
    await page.locator(".nav-item[data-section='advanced']").click();
    await expect(page.locator("#section-advanced")).toHaveClass(/active/);
  });

  test("has add server button", async ({ page }) => {
    const addBtn = page.locator("#btn-add-server");
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toContainText("Add Server");
  });

  test("add server button opens modal", async ({ page }) => {
    await page.locator("#btn-add-server").click();
    await expect(page.locator("#server-modal")).toBeVisible();
    await expect(page.locator("#modal-title")).toHaveText("Add Server");
  });

  test("server form has required fields", async ({ page }) => {
    await page.locator("#btn-add-server").click();
    await expect(page.locator("#server-name")).toBeVisible();
    await expect(page.locator("#server-url")).toBeVisible();
    await expect(page.locator("#server-auth")).toBeVisible();
  });

  test("can close server modal", async ({ page }) => {
    await page.locator("#btn-add-server").click();
    await expect(page.locator("#server-modal")).toBeVisible();
    await page.locator("#modal-close").click();
    await expect(page.locator("#server-modal")).toBeHidden();
  });

  test("has auto-discover section", async ({ page }) => {
    const discoverBtn = page.locator("#btn-auto-discover");
    await expect(discoverBtn).toBeVisible();
  });

  test("general section has toggle switches", async ({ page }) => {
    await page.locator(".nav-item[data-section='general']").click();
    await expect(page.locator("#setting-auto-scan")).toBeVisible();
    await expect(page.locator("#setting-highlight")).toBeVisible();
    await expect(page.locator("#setting-notifications")).toBeVisible();
  });

  test("advanced section has numeric inputs", async ({ page }) => {
    await page.locator(".nav-item[data-section='advanced']").click();
    await expect(page.locator("#setting-health-interval")).toBeVisible();
    await expect(page.locator("#setting-max-history")).toBeVisible();
    await expect(page.locator("#setting-max-queue")).toBeVisible();
  });

  test("about section displays version info", async ({ page }) => {
    await page.locator(".nav-item[data-section='about']").click();
    await expect(page.locator("#section-about")).toHaveClass(/active/);
    await expect(page.locator(".about-card")).toContainText("BobaLink");
  });
});
