import type { Config } from "jest";

/**
 * Jest test configuration for BobaLink extension.
 * Supports unit tests with jsdom environment for DOM-related tests
 * and node environment for pure logic tests.
 */
const config: Config = {
  /**
   * Use ts-jest preset for TypeScript support.
   */
  preset: "ts-jest/presets/default-esm",

  /**
   * Test environment - jsdom for DOM-related tests.
   * Individual test files can override via @jest-environment comment.
   */
  testEnvironment: "jsdom",

  /**
   * Root directories for test discovery.
   */
  roots: ["<rootDir>/tests/unit", "<rootDir>/src"],

  /**
   * Test file patterns to match.
   */
  testMatch: [
    "**/tests/unit/**/*.test.ts",
    "**/src/**/*.test.ts",
  ],

  /**
   * Module path aliases matching tsconfig paths.
   */
  moduleNameMapper: {
    "^~/(.*)$": "<rootDir>/src/$1",
    "^@/(.*)$": "<rootDir>/src/$1",
  },

  /**
   * Transform TypeScript files with ts-jest.
   */
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        useESM: true,
        tsconfig: {
          jsx: "preserve",
          esModuleInterop: true,
        },
      },
    ],
  },

  /**
   * File extensions Jest will look for.
   */
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json", "node"],

  /**
   * Coverage collection patterns.
   */
  collectCoverageFrom: [
    "src/**/*.ts",
    "!src/**/*.d.ts",
    "!src/**/index.ts",
    "!src/assets/**",
    "!src/popup/**",
    "!src/options/**",
    "!src/content/**",
    "!src/background/**",
  ],

  /**
   * Coverage thresholds - enforce 80%+ coverage.
   */
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },

  /**
   * Coverage report formats.
   */
  coverageReporters: ["text", "text-summary", "lcov", "html"],

  /**
   * Coverage output directory.
   */
  coverageDirectory: "<rootDir>/coverage",

  /**
   * Setup files to run after Jest is initialized.
   */
  setupFilesAfterEnv: ["<rootDir>/tests/unit/setup.ts"],

  /**
   * Mock chrome API for tests.
   */
  setupFiles: ["<rootDir>/tests/unit/chrome-mock.ts"],

  /**
   * Clear mocks between tests.
   */
  clearMocks: true,

  /**
   * Restore mocks after each test.
   */
  restoreMocks: true,

  /**
   * Maximum test timeout in milliseconds.
   */
  testTimeout: 10000,

  /**
   * Verbose output for detailed test results.
   */
  verbose: true,

  /**
   * Extensions to treat as ESM.
   */
  extensionsToTreatAsEsm: [".ts"],

  /**
   * Globals available in all test files.
   */
  globals: {
    "ts-jest": {
      useESM: true,
    },
  },
};

export default config;
