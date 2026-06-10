/**
 * @fileoverview WXT background entrypoint (MV3 service worker).
 *
 * Thin wrapper: the real message-hub logic lives in `src/background/index.ts`
 * ({@link initBackground}). This entrypoint exists so WXT generates the
 * `background.service_worker` manifest entry and bundles the worker; it keeps
 * the logic module unit-testable in isolation (the 287-test suite imports
 * `../background` directly).
 *
 * {@link initBackground} is idempotent (guarded by an internal `registered`
 * flag), so even if the logic module's own real-context auto-run fires on
 * import under the bundled worker, calling it again here is a safe no-op.
 *
 * @module entrypoints/background
 */
import { defineBackground } from "wxt/sandbox";

import { initBackground } from "../background";

export default defineBackground(() => {
  initBackground();
});
