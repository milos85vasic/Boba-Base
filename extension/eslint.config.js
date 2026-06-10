// @ts-check
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

/**
 * ESLint flat config (ESLint 9) for BobaLink.
 *
 * Type-aware lint mirroring the reference's strict posture:
 * no-explicit-any (error), no-floating-promises (error),
 * no-misused-promises (error), prefer-nullish-coalescing (error),
 * eqeqeq (error), no-unused-vars with ^_ ignore. tests/** relaxes the
 * any/unsafe rules.
 */
export default tseslint.config(
  {
    ignores: ["node_modules/", ".output/", ".wxt/", "coverage/", "dist/"],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.configs.strict,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/prefer-nullish-coalescing": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-console": ["warn", { allow: ["error", "warn", "info", "debug"] }],
    },
  },
  {
    files: ["tests/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-unsafe-argument": "off",
    },
  },
);
