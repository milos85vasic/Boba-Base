import { normalizeApiBase, resolveApiBase } from './api-base';

describe('api-base (BUG-5 configurable API base)', () => {
  describe('normalizeApiBase', () => {
    it('returns empty string for null/undefined/empty', () => {
      expect(normalizeApiBase(null)).toBe('');
      expect(normalizeApiBase(undefined)).toBe('');
      expect(normalizeApiBase('')).toBe('');
    });

    it('strips trailing slashes so concatenation never doubles up', () => {
      expect(normalizeApiBase('https://host:7187/')).toBe('https://host:7187');
      expect(normalizeApiBase('https://host:7187///')).toBe('https://host:7187');
    });

    it('leaves a clean base unchanged', () => {
      expect(normalizeApiBase('https://host:7187')).toBe('https://host:7187');
    });
  });

  describe('resolveApiBase', () => {
    const w = window as unknown as { __BOBA_API_BASE__?: string };

    afterEach(() => {
      delete w.__BOBA_API_BASE__;
      document.querySelector('meta[name="boba-api-base"]')?.remove();
    });

    it('defaults to same-origin ("") when nothing is configured (back-compat)', () => {
      expect(resolveApiBase()).toBe('');
    });

    it('prefers window.__BOBA_API_BASE__ and normalizes it', () => {
      w.__BOBA_API_BASE__ = 'https://remote:7187/';
      expect(resolveApiBase()).toBe('https://remote:7187');
    });

    it('falls back to the <meta name="boba-api-base"> tag', () => {
      const meta = document.createElement('meta');
      meta.setAttribute('name', 'boba-api-base');
      meta.setAttribute('content', 'https://meta-host:7187/');
      document.head.appendChild(meta);
      expect(resolveApiBase()).toBe('https://meta-host:7187');
    });

    it('window global wins over the meta tag', () => {
      w.__BOBA_API_BASE__ = 'https://win:7187';
      const meta = document.createElement('meta');
      meta.setAttribute('name', 'boba-api-base');
      meta.setAttribute('content', 'https://meta:7187');
      document.head.appendChild(meta);
      expect(resolveApiBase()).toBe('https://win:7187');
    });
  });
});
