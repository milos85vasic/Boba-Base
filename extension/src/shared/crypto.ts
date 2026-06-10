/**
 * @fileoverview AES-256-GCM credential encryption for BobaLink.
 *
 * Provides secure encryption and decryption of sensitive data (passwords, API keys)
 * using AES-256-GCM via the Web Crypto API. Keys are derived from a user-supplied
 * passphrase using PBKDF2 with random salts.
 *
 * All encrypted data includes the salt, IV, and auth tag, making each
 * encryption operation independent and secure.
 *
 * @module shared/crypto
 */

import { ENCRYPTION } from "./constants";
import { StorageError } from "./errors";

/**
 * Encrypted data bundle containing everything needed for decryption.
 * Stored as a JSON-serializable object.
 */
export interface EncryptedBundle {
  /** Base64-encoded salt used for key derivation */
  readonly salt: string;

  /** Base64-encoded initialization vector */
  readonly iv: string;

  /** Base64-encoded ciphertext with auth tag appended */
  readonly ciphertext: string;

  /** Key version for future migration support */
  readonly version: number;
}

/**
 * Derive an AES-256-GCM key from a passphrase and salt using PBKDF2.
 *
 * @param passphrase - User-supplied passphrase
 * @param salt - Random salt bytes
 * @returns Derived CryptoKey for AES-GCM operations
 */
async function deriveKey(
  passphrase: string,
  salt: Uint8Array<ArrayBuffer>,
): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const passphraseData = encoder.encode(passphrase);

  // Import the passphrase as a key material
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    passphraseData,
    { name: ENCRYPTION.KDF_ALGORITHM },
    false,
    ["deriveKey"],
  );

  // Derive the actual AES key using PBKDF2
  return crypto.subtle.deriveKey(
    {
      name: ENCRYPTION.KDF_ALGORITHM,
      salt,
      iterations: ENCRYPTION.KDF_ITERATIONS,
      hash: ENCRYPTION.KDF_HASH,
    },
    keyMaterial,
    {
      name: ENCRYPTION.ALGORITHM,
      length: ENCRYPTION.KEY_LENGTH_BITS,
    },
    false,
    ["encrypt", "decrypt"],
  );
}

/**
 * Generate a random byte array of the specified length.
 *
 * @param length - Number of bytes to generate
 * @returns Random bytes
 */
function generateRandomBytes(length: number): Uint8Array<ArrayBuffer> {
  return crypto.getRandomValues(new Uint8Array(length));
}

/**
 * Convert a Uint8Array to a Base64 string.
 *
 * @param bytes - Bytes to encode
 * @returns Base64 string
 */
function bytesToBase64(bytes: Uint8Array): string {
  // Use Uint8Array directly to avoid Node.js Buffer dependency
  const chars: string[] = [];
  for (let i = 0; i < bytes.length; i++) {
    chars.push(String.fromCharCode(bytes[i] as number));
  }
  return btoa(chars.join(""));
}

/**
 * Convert a Base64 string to a Uint8Array.
 *
 * @param base64 - Base64 string to decode
 * @returns Decoded bytes
 */
function base64ToBytes(base64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Encrypt a plaintext string using AES-256-GCM.
 *
 * The passphrase is used to derive the encryption key via PBKDF2.
 * Each call generates a fresh random salt and IV, ensuring unique ciphertexts.
 *
 * @param plaintext - The sensitive data to encrypt
 * @param passphrase - User passphrase for key derivation
 * @returns Encrypted bundle containing salt, IV, and ciphertext
 *
 * @example
 * ```typescript
 * const encrypted = await encrypt("my-secret-password", "user-passphrase");
 * // Store encrypted.salt, encrypted.iv, encrypted.ciphertext
 * ```
 */
export async function encrypt(
  plaintext: string,
  passphrase: string,
): Promise<EncryptedBundle> {
  if (!plaintext) {
    throw new StorageError("Cannot encrypt empty plaintext");
  }
  if (!passphrase) {
    throw new StorageError("Passphrase is required for encryption");
  }

  try {
    // Generate random salt and IV
    const salt = generateRandomBytes(ENCRYPTION.SALT_LENGTH_BYTES);
    const iv = generateRandomBytes(ENCRYPTION.IV_LENGTH_BYTES);

    // Derive the encryption key
    const key = await deriveKey(passphrase, salt);

    // Encrypt the plaintext
    const encoder = new TextEncoder();
    const plaintextData = encoder.encode(plaintext);

    const ciphertextBuffer = await crypto.subtle.encrypt(
      {
        name: ENCRYPTION.ALGORITHM,
        iv,
        tagLength: 128, // GCM authentication tag is 128 bits
      },
      key,
      plaintextData,
    );

    const ciphertext = new Uint8Array(ciphertextBuffer);

    return {
      salt: bytesToBase64(salt),
      iv: bytesToBase64(iv),
      ciphertext: bytesToBase64(ciphertext),
      version: ENCRYPTION.CURRENT_KEY_VERSION,
    };
  } catch (cause) {
    throw new StorageError("Encryption failed", {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
    });
  }
}

/**
 * Decrypt an encrypted bundle back to plaintext.
 *
 * @param bundle - The encrypted bundle from encrypt()
 * @param passphrase - The same passphrase used for encryption
 * @returns The original plaintext string
 *
 * @example
 * ```typescript
 * const plaintext = await decrypt(encryptedBundle, "user-passphrase");
 * console.log(plaintext); // "my-secret-password"
 * ```
 */
export async function decrypt(
  bundle: EncryptedBundle,
  passphrase: string,
): Promise<string> {
  if (!passphrase) {
    throw new StorageError("Passphrase is required for decryption");
  }

  try {
    // Decode the stored values
    const salt = base64ToBytes(bundle.salt);
    const iv = base64ToBytes(bundle.iv);
    const ciphertext = base64ToBytes(bundle.ciphertext);

    // Derive the same key (same passphrase + salt = same key)
    const key = await deriveKey(passphrase, salt);

    // Decrypt the ciphertext
    const plaintextBuffer = await crypto.subtle.decrypt(
      {
        name: ENCRYPTION.ALGORITHM,
        iv,
        tagLength: 128,
      },
      key,
      ciphertext,
    );

    const decoder = new TextDecoder();
    return decoder.decode(plaintextBuffer);
  } catch (cause) {
    throw new StorageError("Decryption failed. The passphrase may be incorrect.", {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
    });
  }
}

/**
 * Generate a secure random passphrase for first-time setup.
 * Creates a 32-byte random value encoded as base64.
 *
 * @returns A secure random passphrase string
 */
export function generateSecurePassphrase(): string {
  const bytes = generateRandomBytes(32);
  return bytesToBase64(bytes);
}

/**
 * Check if a string appears to be encrypted data (has the bundle structure).
 *
 * @param value - Value to check
 * @returns True if the value looks like an encrypted bundle
 */
export function isEncrypted(value: unknown): value is EncryptedBundle {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.salt === "string" &&
    typeof v.iv === "string" &&
    typeof v.ciphertext === "string" &&
    typeof v.version === "number"
  );
}

/**
 * Hash a string using SHA-256 for non-reversible fingerprinting.
 * Used for creating non-sensitive identifiers from sensitive data.
 *
 * @param input - String to hash
 * @returns Hex-encoded SHA-256 digest
 */
export async function sha256(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashBytes = new Uint8Array(hashBuffer);

  // Convert to hex
  return Array.from(hashBytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Hash a string synchronously using a simple hash function.
 * NOT cryptographically secure - used only for cache keys and identifiers.
 *
 * @param input - String to hash
 * @returns Numeric hash code
 */
export function simpleHash(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}
