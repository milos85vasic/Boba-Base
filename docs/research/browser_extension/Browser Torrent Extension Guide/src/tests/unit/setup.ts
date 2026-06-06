/**
 * Jest test setup file.
 *
 * Configures the test environment with necessary globals and polyfills
 * for testing browser extension code in a Node.js environment.
 */

// Extend jest matchers
import "@testing-library/jest-dom";

// Set up chrome API mock if not already provided
declare global {
  // eslint-disable-next-line no-var
  var chrome: typeof import("../fixtures/chrome-mock").chromeMock;
}

// Suppress console output during tests unless DEBUG is set
if (!process.env.DEBUG) {
  const noop = (): void => {};

  // Store original methods for potential restoration
  const originalConsole = {
    log: console.log,
    debug: console.debug,
    info: console.info,
    warn: console.warn,
    error: console.error,
  };

  beforeAll(() => {
    console.log = noop;
    console.debug = noop;
    console.info = noop;
    console.warn = noop;
    // Keep error visible for debugging test failures
  });

  afterAll(() => {
    console.log = originalConsole.log;
    console.debug = originalConsole.debug;
    console.info = originalConsole.info;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
  });
}

// Increase default timeout for async operations
jest.setTimeout(10000);
