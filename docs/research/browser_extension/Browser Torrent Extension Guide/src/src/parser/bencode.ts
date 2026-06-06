/**
 * @fileoverview Bencode encoder/decoder for BobaLink.
 *
 * Implements the Bencode serialization format used by BitTorrent.
 * Supports all four Bencode types: integers, byte strings, lists, and dictionaries.
 *
 * Uses Uint8Array for binary data handling with zero external dependencies.
 * Handles both UTF-8 string and raw binary data modes.
 *
 * @see https://wiki.theory.org/BitTorrentSpecification#Bencoding
 *
 * @module parser/bencode
 */

import { ParseError } from "../shared/errors";

/** Valid Bencode value types. */
export type BencodeValue =
  | number
  | string
  | Uint8Array
  | BencodeValue[]
  | { readonly [key: string]: BencodeValue };

/** Bencode dictionary type. */
export type BencodeDict = { readonly [key: string]: BencodeValue };

/** Decoder state tracking current position in the byte array. */
interface DecoderState {
  data: Uint8Array;
  pos: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Encoder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Encode a value into Bencode format.
 *
 * @param value - Value to encode (number, string, Uint8Array, array, or object)
 * @returns Bencode-encoded byte array
 */
export function encode(value: BencodeValue): Uint8Array {
  const parts: Uint8Array[] = [];
  encodeValue(value, parts);

  // Concatenate all parts
  const totalLength = parts.reduce((sum, p) => sum + p.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

/**
 * Recursively encode a value, appending parts to the array.
 *
 * @param value - Value to encode
 * @param parts - Array to append encoded chunks to
 */
function encodeValue(value: BencodeValue, parts: Uint8Array[]): void {
  if (typeof value === "number") {
    encodeInteger(value, parts);
  } else if (typeof value === "string") {
    encodeString(value, parts);
  } else if (value instanceof Uint8Array) {
    encodeBytes(value, parts);
  } else if (Array.isArray(value)) {
    encodeList(value, parts);
  } else if (value !== null && typeof value === "object") {
    encodeDict(value as BencodeDict, parts);
  } else {
    throw new ParseError(`Cannot bencode value of type ${typeof value}`);
  }
}

/**
 * Encode an integer: i<e>N</e>
 *
 * @param value - Integer value
 * @param parts - Parts array
 */
function encodeInteger(value: number, parts: Uint8Array[]): void {
  if (!Number.isInteger(value)) {
    throw new ParseError(`Bencode integers must be whole numbers, got: ${value}`);
  }
  const str = `i${value}e`;
  parts.push(textEncoder.encode(str));
}

/**
 * Encode a string as UTF-8 bytes: <length>:<content>
 *
 * @param value - String value
 * @param parts - Parts array
 */
function encodeString(value: string, parts: Uint8Array[]): void {
  const bytes = textEncoder.encode(value);
  encodeBytes(bytes, parts);
}

/**
 * Encode raw bytes: <length>:<content>
 *
 * @param bytes - Byte array
 * @param parts - Parts array
 */
function encodeBytes(bytes: Uint8Array, parts: Uint8Array[]): void {
  const prefix = textEncoder.encode(`${bytes.length}:`);
  parts.push(prefix);
  parts.push(bytes);
}

/**
 * Encode a list: l<contents>e
 *
 * @param list - Array of values
 * @param parts - Parts array
 */
function encodeList(list: BencodeValue[], parts: Uint8Array[]): void {
  parts.push(new Uint8Array([0x6c])); // 'l'
  for (const item of list) {
    encodeValue(item, parts);
  }
  parts.push(new Uint8Array([0x65])); // 'e'
}

/**
 * Encode a dictionary: d<key><value>...e
 * Keys must be strings and are sorted lexicographically.
 *
 * @param dict - Object with string keys
 * @param parts - Parts array
 */
function encodeDict(dict: BencodeDict, parts: Uint8Array[]): void {
  parts.push(new Uint8Array([0x64])); // 'd'

  // Sort keys lexicographically (required by BitTorrent spec)
  const sortedKeys = Object.keys(dict).sort();

  for (const key of sortedKeys) {
    encodeString(key, parts);
    encodeValue(dict[key], parts);
  }

  parts.push(new Uint8Array([0x65])); // 'e'
}

// ─────────────────────────────────────────────────────────────────────────────
// Decoder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Decode a Bencode-encoded byte array.
 *
 * @param data - Bencode data to decode
 * @param options - Decoding options
 * @returns Decoded value
 * @throws ParseError if data is invalid
 */
export function decode(
  data: Uint8Array,
  options: { encoding?: "utf-8" | "binary" } = {},
): BencodeValue {
  const state: DecoderState = { data, pos: 0 };
  const result = decodeValue(state, options.encoding ?? "utf-8");

  // Check for trailing data
  if (state.pos !== data.length) {
    throw new ParseError(
      `Trailing data after bdecode: ${data.length - state.pos} bytes remaining`,
    );
  }

  return result;
}

/**
 * Decode a value from the current position.
 *
 * @param state - Decoder state
 * @param encoding - How to decode byte strings
 * @returns Decoded value
 */
function decodeValue(
  state: DecoderState,
  encoding: "utf-8" | "binary",
): BencodeValue {
  if (state.pos >= state.data.length) {
    throw new ParseError("Unexpected end of bencode data");
  }

  const byte = state.data[state.pos];

  if (byte === 0x69) {
    // 'i' - integer
    return decodeInteger(state);
  } else if (byte === 0x6c) {
    // 'l' - list
    return decodeList(state, encoding);
  } else if (byte === 0x64) {
    // 'd' - dictionary
    return decodeDict(state, encoding);
  } else if (byte >= 0x30 && byte <= 0x39) {
    // '0'-'9' - byte string
    return decodeByteString(state, encoding);
  } else {
    throw new ParseError(
      `Unexpected byte at position ${state.pos}: 0x${byte.toString(16).padStart(2, "0")}`,
    );
  }
}

/**
 * Decode an integer: i<number>e
 *
 * @param state - Decoder state
 * @returns Decoded integer
 */
function decodeInteger(state: DecoderState): number {
  // Skip 'i'
  state.pos++;

  let negative = false;
  if (state.data[state.pos] === 0x2d) {
    // '-'
    negative = true;
    state.pos++;
  }

  let value = 0;
  let hasDigits = false;

  while (state.pos < state.data.length) {
    const byte = state.data[state.pos];
    if (byte === 0x65) {
      // 'e' - end of integer
      state.pos++;
      if (!hasDigits) {
        throw new ParseError("Empty integer at position " + (state.pos - 1));
      }
      return negative ? -value : value;
    }

    if (byte < 0x30 || byte > 0x39) {
      throw new ParseError(
        `Invalid digit in integer at position ${state.pos}`,
      );
    }

    hasDigits = true;
    value = value * 10 + (byte - 0x30);
    state.pos++;
  }

  throw new ParseError("Unterminated integer");
}

/**
 * Decode a byte string: <length>:<bytes>
 *
 * @param state - Decoder state
 * @param encoding - How to decode the bytes
 * @returns String or Uint8Array depending on encoding
 */
function decodeByteString(
  state: DecoderState,
  encoding: "utf-8" | "binary",
): string | Uint8Array {
  // Parse length
  let length = 0;
  let hasDigits = false;

  while (state.pos < state.data.length) {
    const byte = state.data[state.pos];
    if (byte === 0x3a) {
      // ':' - separator
      state.pos++;
      if (!hasDigits) {
        throw new ParseError("Empty string length at position " + state.pos);
      }
      break;
    }

    if (byte < 0x30 || byte > 0x39) {
      throw new ParseError(
        `Invalid digit in string length at position ${state.pos}`,
      );
    }

    hasDigits = true;
    length = length * 10 + (byte - 0x30);
    state.pos++;
  }

  if (state.pos + length > state.data.length) {
    throw new ParseError(
      `String extends past end of data: need ${length} bytes at position ${state.pos}, have ${state.data.length - state.pos}`,
    );
  }

  // Extract bytes
  const bytes = state.data.slice(state.pos, state.pos + length);
  state.pos += length;

  if (encoding === "binary") {
    return bytes;
  }

  return textDecoder.decode(bytes);
}

/**
 * Decode a list: l<values>e
 *
 * @param state - Decoder state
 * @param encoding - How to decode byte strings
 * @returns Array of decoded values
 */
function decodeList(
  state: DecoderState,
  encoding: "utf-8" | "binary",
): BencodeValue[] {
  // Skip 'l'
  state.pos++;

  const result: BencodeValue[] = [];

  while (state.pos < state.data.length) {
    if (state.data[state.pos] === 0x65) {
      // 'e' - end of list
      state.pos++;
      return result;
    }
    result.push(decodeValue(state, encoding));
  }

  throw new ParseError("Unterminated list");
}

/**
 * Decode a dictionary: d<key><value>...e
 *
 * @param state - Decoder state
 * @param encoding - How to decode byte strings
 * @returns Decoded dictionary object
 */
function decodeDict(
  state: DecoderState,
  encoding: "utf-8" | "binary",
): BencodeDict {
  // Skip 'd'
  state.pos++;

  const result: Record<string, BencodeValue> = {};

  while (state.pos < state.data.length) {
    if (state.data[state.pos] === 0x65) {
      // 'e' - end of dict
      state.pos++;
      return result;
    }

    // Key must be a byte string
    const key = decodeByteString(state, "utf-8");
    if (typeof key !== "string") {
      throw new ParseError("Dictionary key must be a string");
    }

    const value = decodeValue(state, encoding);
    result[key] = value;
  }

  throw new ParseError("Unterminated dictionary");
}

// ─────────────────────────────────────────────────────────────────────────────
// Text Encoding Utilities
// ─────────────────────────────────────────────────────────────────────────────

/** TextEncoder instance for UTF-8 encoding. */
const textEncoder = new TextEncoder();

/** TextDecoder instance for UTF-8 decoding. */
const textDecoder = new TextDecoder("utf-8");

/**
 * Convert a Uint8Array to a hex string.
 *
 * @param bytes - Byte array to convert
 * @returns Hex-encoded string
 */
export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Convert a hex string to a Uint8Array.
 *
 * @param hex - Hex string to convert
 * @returns Byte array
 */
export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

/**
 * Compute SHA-1 hash of data using Web Crypto API.
 *
 * @param data - Data to hash
 * @returns Hex-encoded SHA-1 digest
 */
export async function sha1(data: Uint8Array): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-1", data);
  const hashBytes = new Uint8Array(hashBuffer);
  return bytesToHex(hashBytes);
}
