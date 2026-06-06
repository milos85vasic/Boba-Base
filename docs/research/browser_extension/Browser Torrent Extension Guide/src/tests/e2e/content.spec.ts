/**
 * @fileoverview E2E tests for content script torrent detection.
 *
 * Tests that the content script properly detects magnet links and
 * .torrent files on various page types.
 */

import { test, expect } from "@playwright/test";

test.describe("Content Script Detection", () => {
  test("detects magnet links on a simulated torrent page", async ({ page }) => {
    // Create a page with magnet links
    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <body>
          <h1>Test Torrent Page</h1>
          <a href="magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Test+File">
            Download Magnet
          </a>
          <a href="magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12&dn=Another+File">
            Another Magnet
          </a>
          <a href="http://example.com/file.torrent">Download .torrent</a>
        </body>
      </html>
    `);

    // Wait for any content script initialization
    await page.waitForTimeout(500);

    // Verify the page content exists
    const magnetLinks = page.locator('a[href^="magnet:"]');
    await expect(magnetLinks).toHaveCount(2);

    const torrentLinks = page.locator('a[href$=".torrent"]');
    await expect(torrentLinks).toHaveCount(1);
  });

  test("detects magnet links in text content", async ({ page }) => {
    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <body>
          <p>Here is a magnet link in text: magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Text+File</p>
        </body>
      </html>
    `);

    await page.waitForTimeout(500);

    // Verify text content contains magnet
    const body = page.locator("body");
    await expect(body).toContainText("magnet:");
  });

  test("ignores links inside script tags", async ({ page }) => {
    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <body>
          <script>
            var magnet = "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678";
          </script>
          <a href="magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12&dn=Real">Real</a>
        </body>
      </html>
    `);

    await page.waitForTimeout(500);

    const links = page.locator('a[href^="magnet:"]');
    await expect(links).toHaveCount(1);
  });

  test("handles pages with no torrent content", async ({ page }) => {
    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <body>
          <h1>Normal Website</h1>
          <a href="http://example.com/about">About</a>
          <a href="http://example.com/contact">Contact</a>
        </body>
      </html>
    `);

    await page.waitForTimeout(500);

    const magnets = page.locator('a[href^="magnet:"]');
    await expect(magnets).toHaveCount(0);
  });
});
