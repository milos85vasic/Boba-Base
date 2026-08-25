/**
 * Minimal ambient declarations for the Node built-ins used by
 * `src/app/models/style-contrast.spec.ts`, which reads the real
 * stylesheet sources off disk so a token used as a BACKGROUND is inside
 * the contrast oracle's pair set by construction (BOB-164 round 2).
 *
 * WHY A SHIM RATHER THAN `@types/node` (§11.4.6): the full type package
 * is not installed in this workspace, and pulling a new devDependency in
 * for three function signatures is a larger change than declaring them.
 * The declarations below are deliberately NARROW — only the members the
 * spec actually calls — so they cannot silently type-approve unrelated
 * Node API use in application code.
 *
 * These are TYPES ONLY. Vitest runs under Node, so the real
 * implementations are supplied by the runtime; nothing here reaches the
 * browser bundle (`tsconfig.app.json` compiles no `.spec.ts`).
 */

declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string;
  export function readdirSync(path: string): string[];
  export function statSync(path: string): { isDirectory(): boolean };
}

declare module 'node:path' {
  export function join(...parts: string[]): string;
  export function relative(from: string, to: string): string;
}

declare const process: { cwd(): string };
