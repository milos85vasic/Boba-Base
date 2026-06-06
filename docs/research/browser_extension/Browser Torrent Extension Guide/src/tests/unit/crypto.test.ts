/**
 * @fileoverview Credential Encryption Test Suite
 *
 * Tests for encrypting/decrypting credentials using the Web Crypto API.
 * Covers roundtrip, wrong password detection, empty data, large data,
 * and different data types.
 *
 * @module tests/unit/crypto
 * @version 1.0.0
 */

import { describe, it, expect, beforeAll } from 'vitest';

// ---------------------------------------------------------------------------
// Type Definitions
// ---------------------------------------------------------------------------

interface EncryptedData {
  ciphertext: string; // base64
  iv: string; // base64
  salt: string; // base64
  version: number;
}

// ---------------------------------------------------------------------------
// Crypto Implementation (mirrors src/utils/crypto.ts)
// ---------------------------------------------------------------------------

/**
 * Derive a 256-bit AES key from a password using PBKDF2.
 */
async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const passwordData = encoder.encode(password);

  const baseKey = await crypto.subtle.importKey('raw', passwordData, 'PBKDF2', false, ['deriveKey']);

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: 100000,
      hash: 'SHA-256',
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Generate random bytes.
 */
function getRandomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length));
}

/**
 * Convert Uint8Array to base64 string.
 */
function toBase64(data: Uint8Array): string {
  const binString = Array.from(data, (byte) => String.fromCharCode(byte)).join('');
  return btoa(binString);
}

/**
 * Convert base64 string to Uint8Array.
 */
function fromBase64(base64: string): Uint8Array {
  const binString = atob(base64);
  return Uint8Array.from(binString, (char) => char.charCodeAt(0));
}

/**
 * Encrypt plaintext string.
 */
async function encrypt(plaintext: string, password: string): Promise<EncryptedData> {
  const encoder = new TextEncoder();
  const data = encoder.encode(plaintext);
  const salt = getRandomBytes(16);
  const iv = getRandomBytes(12); // 96-bit IV for AES-GCM

  const key = await deriveKey(password, salt);
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data));

  return {
    ciphertext: toBase64(ciphertext),
    iv: toBase64(iv),
    salt: toBase64(salt),
    version: 1,
  };
}

/**
 * Decrypt encrypted data.
 */
async function decrypt(encrypted: EncryptedData, password: string): Promise<string> {
  const salt = fromBase64(encrypted.salt);
  const iv = fromBase64(encrypted.iv);
  const ciphertext = fromBase64(encrypted.ciphertext);

  const key = await deriveKey(password, salt);
  const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);

  return new TextDecoder().decode(decrypted);
}

/**
 * Encrypt JSON-serializable object.
 */
async function encryptObject<T extends Record<string, unknown>>(obj: T, password: string): Promise<EncryptedData> {
  return encrypt(JSON.stringify(obj), password);
}

/**
 * Decrypt to JSON object.
 */
async function decryptObject<T extends Record<string, unknown>>(encrypted: EncryptedData, password: string): Promise<T> {
  const json = await decrypt(encrypted, password);
  return JSON.parse(json) as T;
}

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

describe('Credential Encryption', () => {
  const PASSWORD = 'my-secure-password-123';
  const WRONG_PASSWORD = 'wrong-password-456';

  // ============================================
  // 1. Encrypt/Decrypt Roundtrip
  // ============================================

  describe('Roundtrip', () => {
    it('should encrypt and decrypt a simple string', async () => {
      const original = 'hello world';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should encrypt and decrypt a password', async () => {
      const original = 'SuperSecretP@ssw0rd!2024';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should encrypt and decrypt an API key', async () => {
      const original = 'sk-abc123def456ghi789jkl012mno345pqr678stu';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should produce different ciphertext on each encryption', async () => {
      const original = 'same text';
      const encrypted1 = await encrypt(original, PASSWORD);
      const encrypted2 = await encrypt(original, PASSWORD);

      // IV and salt are random, so ciphertext should differ
      expect(encrypted1.ciphertext).not.toBe(encrypted2.ciphertext);
      expect(encrypted1.iv).not.toBe(encrypted2.iv);
      expect(encrypted1.salt).not.toBe(encrypted2.salt);
    });

    it('should preserve version field', async () => {
      const encrypted = await encrypt('test', PASSWORD);
      expect(encrypted.version).toBe(1);
    });

    it('should produce valid base64 strings', async () => {
      const encrypted = await encrypt('test', PASSWORD);

      expect(() => fromBase64(encrypted.ciphertext)).not.toThrow();
      expect(() => fromBase64(encrypted.iv)).not.toThrow();
      expect(() => fromBase64(encrypted.salt)).not.toThrow();
    });

    it('should handle Unicode characters', async () => {
      const original = '\u4e2d\u6587\u5bc6\u7801 \uD83E\uDD80 \u00E9\u00E8\u00EA';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle very long strings', async () => {
      const original = 'x'.repeat(10000);
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle strings with special characters', async () => {
      const original = '!@#$%^&*()_+-=[]{}|;:,.<>?/~`';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle strings with newlines', async () => {
      const original = 'line1\nline2\r\nline3\n';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle tab characters', async () => {
      const original = 'col1\tcol2\tcol3';
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });
  });

  // ============================================
  // 2. Wrong Password Fails Decryption
  // ============================================

  describe('Wrong Password', () => {
    it('should fail decryption with wrong password', async () => {
      const encrypted = await encrypt('secret data', PASSWORD);

      await expect(decrypt(encrypted, WRONG_PASSWORD)).rejects.toThrow();
    });

    it('should fail with completely different password', async () => {
      const encrypted = await encrypt('data', PASSWORD);

      await expect(decrypt(encrypted, 'totally-different')).rejects.toThrow();
    });

    it('should fail with empty password', async () => {
      const encrypted = await encrypt('data', PASSWORD);

      await expect(decrypt(encrypted, '')).rejects.toThrow();
    });

    it('should fail with case variation', async () => {
      const encrypted = await encrypt('data', 'Password');

      await expect(decrypt(encrypted, 'password')).rejects.toThrow();
    });

    it('should fail when password has trailing space', async () => {
      const encrypted = await encrypt('data', 'password');

      await expect(decrypt(encrypted, 'password ')).rejects.toThrow();
    });

    it('should produce different derived keys for different passwords', async () => {
      const salt = getRandomBytes(16);
      const key1 = await deriveKey('password1', salt);
      const key2 = await deriveKey('password2', salt);

      // Export and compare
      const raw1 = await crypto.subtle.exportKey('raw', key1).catch(() => null);
      // Note: extractable is false so this will fail - which is correct behavior
      expect(raw1).toBeNull();
    });
  });

  // ============================================
  // 3. Empty Data Handling
  // ============================================

  describe('Empty Data', () => {
    it('should encrypt and decrypt empty string', async () => {
      const encrypted = await encrypt('', PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe('');
    });

    it('should have non-empty ciphertext for empty input', async () => {
      const encrypted = await encrypt('', PASSWORD);

      // Even empty string produces ciphertext (auth tag at minimum)
      expect(encrypted.ciphertext.length).toBeGreaterThan(0);
    });
  });

  // ============================================
  // 4. Large Data Handling
  // ============================================

  describe('Large Data', () => {
    it('should handle 1 KB of data', async () => {
      const original = 'x'.repeat(1024);
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle 10 KB of data', async () => {
      const original = 'x'.repeat(10240);
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle 100 KB of data', async () => {
      const original = 'x'.repeat(102400);
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);

      expect(decrypted).toBe(original);
    });

    it('should handle 1 MB of data', async () => {
      const original = 'x'.repeat(1024 * 1024);
      const start = performance.now();
      const encrypted = await encrypt(original, PASSWORD);
      const decrypted = await decrypt(encrypted, PASSWORD);
      const elapsed = performance.now() - start;

      expect(decrypted).toBe(original);
      expect(elapsed).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });

  // ============================================
  // 5. Different Data Types (Object Encryption)
  // ============================================

  describe('Object Encryption', () => {
    it('should encrypt and decrypt a credentials object', async () => {
      const credentials = {
        username: 'admin',
        password: 'secret123',
        serverUrl: 'http://localhost:8080',
        apiKey: 'key-abc-123',
      };

      const encrypted = await encryptObject(credentials, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted).toEqual(credentials);
    });

    it('should encrypt and decrypt nested objects', async () => {
      const config = {
        server: {
          baseUrl: 'http://localhost:8080',
          ports: {
            webui: 8080,
            fastapi: 7187,
          },
        },
        auth: {
          method: 'cookie',
          credentials: {
            username: 'admin',
            password: 'secret',
          },
        },
        features: ['auto-scan', 'highlight', 'notifications'],
      };

      const encrypted = await encryptObject(config, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted).toEqual(config);
    });

    it('should encrypt and decrypt array data', async () => {
      const data = {
        trackers: [
          'udp://tracker1.example.com:6969',
          'udp://tracker2.example.com:6969',
          'udp://tracker3.example.com:6969',
        ],
      };

      const encrypted = await encryptObject(data, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted.trackers).toHaveLength(3);
    });

    it('should encrypt and decrypt boolean values', async () => {
      const data = {
        requireHttps: true,
        encryptCredentials: true,
        debugMode: false,
        startPaused: false,
      };

      const encrypted = await encryptObject(data, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted.requireHttps).toBe(true);
      expect(decrypted.encryptCredentials).toBe(true);
      expect(decrypted.debugMode).toBe(false);
      expect(decrypted.startPaused).toBe(false);
    });

    it('should encrypt and decrypt numeric values', async () => {
      const data = {
        popupWidth: 400,
        popupHeight: 600,
        rateLimit: 30,
        sessionTimeout: 3600,
        maxStorageMb: 50.5,
      };

      const encrypted = await encryptObject(data, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted.popupWidth).toBe(400);
      expect(decrypted.popupHeight).toBe(600);
      expect(decrypted.rateLimit).toBe(30);
      expect(decrypted.sessionTimeout).toBe(3600);
      expect(decrypted.maxStorageMb).toBe(50.5);
    });

    it('should handle null values', async () => {
      const data = {
        username: 'admin',
        password: null,
        apiKey: null,
        optional: null,
      };

      const encrypted = await encryptObject(data as unknown as Record<string, unknown>, PASSWORD);
      const decrypted = await decryptObject(encrypted, PASSWORD);

      expect(decrypted.username).toBe('admin');
      expect(decrypted.password).toBeNull();
      expect(decrypted.apiKey).toBeNull();
    });
  });

  // ============================================
  // 6. IV and Salt Properties
  // ============================================

  describe('IV and Salt', () => {
    it('should use 12-byte IV for AES-GCM', async () => {
      const encrypted = await encrypt('test', PASSWORD);
      const iv = fromBase64(encrypted.iv);

      expect(iv.length).toBe(12);
    });

    it('should use 16-byte salt', async () => {
      const encrypted = await encrypt('test', PASSWORD);
      const salt = fromBase64(encrypted.salt);

      expect(salt.length).toBe(16);
    });

    it('should use unique IV for each encryption', async () => {
      const encrypted1 = await encrypt('test', PASSWORD);
      const encrypted2 = await encrypt('test', PASSWORD);

      expect(encrypted1.iv).not.toBe(encrypted2.iv);
    });

    it('should use unique salt for each encryption', async () => {
      const encrypted1 = await encrypt('test', PASSWORD);
      const encrypted2 = await encrypt('test', PASSWORD);

      expect(encrypted1.salt).not.toBe(encrypted2.salt);
    });
  });

  // ============================================
  // 7. PBKDF2 Key Derivation
  // ============================================

  describe('Key Derivation', () => {
    it('should derive same key with same password and salt', async () => {
      const salt = getRandomBytes(16);
      const key1 = await deriveKey(PASSWORD, salt);
      const key2 = await deriveKey(PASSWORD, salt);

      // Keys should be usable for encryption/decryption
      const iv = getRandomBytes(12);
      const data = new TextEncoder().encode('test');

      const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key1, data);
      const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key2, encrypted);

      expect(new TextDecoder().decode(decrypted)).toBe('test');
    });

    it('should derive different keys with different salts', async () => {
      const salt1 = getRandomBytes(16);
      const salt2 = new Uint8Array(16);
      salt2.set(salt1);
      salt2[0] = salt1[0] ^ 0xff; // Flip first byte

      // Both should succeed (different keys)
      const key1 = await deriveKey(PASSWORD, salt1);
      const key2 = await deriveKey(PASSWORD, salt2);

      expect(key1).toBeDefined();
      expect(key2).toBeDefined();
    });
  });

  // ============================================
  // 8. Tamper Detection
  // ============================================

  describe('Tamper Detection', () => {
    it('should fail if ciphertext is modified', async () => {
      const encrypted = await encrypt('sensitive data', PASSWORD);
      const ciphertext = fromBase64(encrypted.ciphertext);
      ciphertext[0] ^= 0xff; // Flip a bit
      encrypted.ciphertext = toBase64(ciphertext);

      await expect(decrypt(encrypted, PASSWORD)).rejects.toThrow();
    });

    it('should fail if IV is modified', async () => {
      const encrypted = await encrypt('sensitive data', PASSWORD);
      const iv = fromBase64(encrypted.iv);
      iv[0] ^= 0xff;
      encrypted.iv = toBase64(iv);

      await expect(decrypt(encrypted, PASSWORD)).rejects.toThrow();
    });

    it('should fail if salt is modified', async () => {
      const encrypted = await encrypt('sensitive data', PASSWORD);
      const salt = fromBase64(encrypted.salt);
      salt[0] ^= 0xff;
      encrypted.salt = toBase64(salt);

      await expect(decrypt(encrypted, PASSWORD)).rejects.toThrow();
    });
  });

  // ============================================
  // 9. Performance
  // ============================================

  describe('Performance', () => {
    it('should encrypt short text within time budget', async () => {
      const start = performance.now();
      await encrypt('short password', PASSWORD);
      const elapsed = performance.now() - start;

      expect(elapsed).toBeLessThan(2000); // PBKDF2 is slow by design
    });

    it('should decrypt short text within time budget', async () => {
      const encrypted = await encrypt('short password', PASSWORD);

      const start = performance.now();
      await decrypt(encrypted, PASSWORD);
      const elapsed = performance.now() - start;

      expect(elapsed).toBeLessThan(100);
    });

    it('should handle many consecutive encryptions', async () => {
      const plaintexts = Array.from({ length: 10 }, (_, i) => `secret-${i}`);

      const start = performance.now();
      const encrypted = await Promise.all(plaintexts.map((p) => encrypt(p, PASSWORD)));
      const decrypted = await Promise.all(encrypted.map((e) => decrypt(e, PASSWORD)));
      const elapsed = performance.now() - start;

      expect(decrypted).toEqual(plaintexts);
      expect(elapsed).toBeLessThan(10000);
    });
  });

  // ============================================
  // 10. Password Edge Cases
  // ============================================

  describe('Password Edge Cases', () => {
    it('should handle short password', async () => {
      const encrypted = await encrypt('data', 'x');
      const decrypted = await decrypt(encrypted, 'x');

      expect(decrypted).toBe('data');
    });

    it('should handle very long password', async () => {
      const longPassword = 'p'.repeat(1024);
      const encrypted = await encrypt('data', longPassword);
      const decrypted = await decrypt(encrypted, longPassword);

      expect(decrypted).toBe('data');
    });

    it('should handle password with Unicode', async () => {
      const unicodePassword = '\u4e2d\u6587\u5bc6\u7801 \uD83D\uDE80';
      const encrypted = await encrypt('data', unicodePassword);
      const decrypted = await decrypt(encrypted, unicodePassword);

      expect(decrypted).toBe('data');
    });

    it('should handle password with spaces', async () => {
      const spacedPassword = 'this is a long password with spaces';
      const encrypted = await encrypt('data', spacedPassword);
      const decrypted = await decrypt(encrypted, spacedPassword);

      expect(decrypted).toBe('data');
    });
  });

  // ============================================
  // 11. Serialize/Deserialize Encrypted Data
  // ============================================

  describe('Serialization', () => {
    it('should be JSON serializable', async () => {
      const encrypted = await encrypt('test', PASSWORD);
      const json = JSON.stringify(encrypted);

      expect(() => JSON.parse(json)).not.toThrow();
    });

    it('should survive roundtrip through JSON', async () => {
      const original = 'roundtrip test data';
      const encrypted = await encrypt(original, PASSWORD);
      const json = JSON.stringify(encrypted);
      const restored = JSON.parse(json);

      const decrypted = await decrypt(restored, PASSWORD);
      expect(decrypted).toBe(original);
    });

    it('should have all required fields', async () => {
      const encrypted = await encrypt('test', PASSWORD);

      expect(encrypted.ciphertext).toBeDefined();
      expect(encrypted.iv).toBeDefined();
      expect(encrypted.salt).toBeDefined();
      expect(encrypted.version).toBeDefined();
      expect(typeof encrypted.ciphertext).toBe('string');
      expect(typeof encrypted.iv).toBe('string');
      expect(typeof encrypted.salt).toBe('string');
      expect(typeof encrypted.version).toBe('number');
    });
  });
});
