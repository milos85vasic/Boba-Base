/**
 * @fileoverview Bencode encoder/decoder for BobaLink.
 *
 * Implements the Bencode serialization format used by BitTorrent.
 * Supports all four Bencode types: integers, byte strings, lists, and dictionaries.
 *
 * Uses Uint8Array for binary data handling with zero external dependencies.
 * Handles both UTF-8 string and raw binary data modes.
 *
 * Ported into the BobaLink extension (Phase 2). Made to compile under the
 * extension's strict tsconfig (`strict`, `noUncheckedIndexedAccess`,
 * `exactOptionalPropertyTypes`) — every indexed byte read is guarded so an
 * out-of-range access (which TS types as `number | undefined`) can never reach
 * arithmetic or comparison without an explicit defined-value check.
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

/** Byte constant for ASCII 'i' (integer prefix). */
const BYTE_I = 0x69;
/** Byte constant for ASCII 'l' (list prefix). */
const BYTE_L = 0x6c;
/** Byte constant for ASCII 'd' (dict prefix). */
const BYTE_D = 0x64;
/** Byte constant for ASCII 'e' (container/integer terminator). */
const BYTE_E = 0x65;
/** Byte constant for ASCII ':' (string length separator). */
const BYTE_COLON = 0x3a;
/** Byte constant for ASCII '-' (negative sign). */
const BYTE_MINUS = 0x2d;
/** Byte constant for ASCII '0'. */
const BYTE_0 = 0x30;
/** Byte constant for ASCII '9'. */
const BYTE_9 = 0x39;

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
    encodeDict(value, parts);
  } else {
    throw new ParseError(`Cannot bencode value of type ${typeof value}`);
  }
}

/**
 * Encode an integer: i<N>e
 *
 * @param value - Integer value
 * @param parts - Parts array
 */
function encodeInteger(value: number, parts: Uint8Array[]): void {
  if (!Number.isInteger(value)) {
    throw new ParseError(
      `Bencode integers must be whole numbers, got: ${value}`,
    );
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
  parts.push(new Uint8Array([BYTE_L])); // 'l'
  for (const item of list) {
    encodeValue(item, parts);
  }
  parts.push(new Uint8Array([BYTE_E])); // 'e'
}

/**
 * Encode a dictionary: d<key><value>...e
 * Keys must be strings and are sorted lexicographically.
 *
 * @param dict - Object with string keys
 * @param parts - Parts array
 */
function encodeDict(dict: BencodeDict, parts: Uint8Array[]): void {
  parts.push(new Uint8Array([BYTE_D])); // 'd'

  // Sort keys lexicographically (required by BitTorrent spec).
  // Object.keys + raw .sort() compares by UTF-16 code unit, which equals the
  // byte order for the ASCII keys used in torrent dictionaries.
  const sortedKeys = Object.keys(dict).sort();

  for (const key of sortedKeys) {
    // `dict[key]` is `BencodeValue | undefined` under noUncheckedIndexedAccess,
    // but `key` came straight from `Object.keys(dict)` so the entry is present.
    const entry = dict[key] as BencodeValue;
    encodeString(key, parts);
    encodeValue(entry, parts);
  }

  parts.push(new Uint8Array([BYTE_E])); // 'e'
}

// ─────────────────────────────────────────────────────────────────────────────
// Decoder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Read the byte at the current decoder position.
 *
 * Centralises the `noUncheckedIndexedAccess` guard: an out-of-range read is a
 * malformed-input condition (truncated data), surfaced as a ParseError rather
 * than letting `undefined` leak into arithmetic.
 *
 * @param state - Decoder state
 * @returns The byte (0-255) at `state.pos`
 * @throws ParseError if the position is past the end of the data
 */
function byteAt(state: DecoderState): number {
  const byte = state.data[state.pos];
  if (byte === undefined) {
    throw new ParseError("Unexpected end of bencode data");
  }
  return byte;
}

/** Whether a byte is an ASCII digit '0'-'9'. */
function isDigit(byte: number): boolean {
  return byte >= BYTE_0 && byte <= BYTE_9;
}

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

  const byte = byteAt(state);

  if (byte === BYTE_I) {
    // 'i' - integer
    return decodeInteger(state);
  } else if (byte === BYTE_L) {
    // 'l' - list
    return decodeList(state, encoding);
  } else if (byte === BYTE_D) {
    // 'd' - dictionary
    return decodeDict(state, encoding);
  } else if (isDigit(byte)) {
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
  if (state.data[state.pos] === BYTE_MINUS) {
    // '-'
    negative = true;
    state.pos++;
  }

  let value = 0;
  let hasDigits = false;

  while (state.pos < state.data.length) {
    const byte = byteAt(state);
    if (byte === BYTE_E) {
      // 'e' - end of integer
      state.pos++;
      if (!hasDigits) {
        throw new ParseError(
          "Empty integer at position " + (state.pos - 1),
        );
      }
      return negative ? -value : value;
    }

    if (!isDigit(byte)) {
      throw new ParseError(
        `Invalid digit in integer at position ${state.pos}`,
      );
    }

    hasDigits = true;
    value = value * 10 + (byte - BYTE_0);
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
    const byte = byteAt(state);
    if (byte === BYTE_COLON) {
      // ':' - separator
      state.pos++;
      if (!hasDigits) {
        throw new ParseError(
          "Empty string length at position " + state.pos,
        );
      }
      break;
    }

    if (!isDigit(byte)) {
      throw new ParseError(
        `Invalid digit in string length at position ${state.pos}`,
      );
    }

    hasDigits = true;
    length = length * 10 + (byte - BYTE_0);
    state.pos++;
  }

  // If we exited the loop without finding ':' (ran off the end) the length
  // prefix was never terminated.
  if (!hasDigits) {
    throw new ParseError("Unterminated string length prefix");
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
    if (byteAt(state) === BYTE_E) {
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
    if (byteAt(state) === BYTE_E) {
      // 'e' - end of dict
      state.pos++;
      return result;
    }

    // Key must be a byte string (decoded as UTF-8 regardless of value encoding).
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
// Raw info-dict slice extraction (for correct infohash computation)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Locate and return the RAW bencoded bytes of the top-level `info` value,
 * exactly as they appear in the input buffer.
 *
 * The BitTorrent infohash is `SHA-1(the raw bencoded info dictionary)` — NOT a
 * re-encode of a decoded value. A decode-then-re-encode round-trip mangles the
 * binary `info.pieces` field (20-byte SHA-1 hashes full of bytes 0x80–0xff): a
 * UTF-8 decode of those bytes is lossy, so the re-encoded bytes differ from the
 * originals and the computed infohash is WRONG for any real torrent. This
 * helper sidesteps that entirely by returning the original byte slice.
 *
 * The outer dictionary is walked structurally (tracking byte offsets) so the
 * `info` value's start and end positions in the buffer are known; the slice
 * between them is returned untouched. The walk reuses the same decode machinery
 * (in "binary" mode, which is lossless) purely to advance the cursor — its
 * decoded values are discarded; only the offsets matter.
 *
 * @param data - Raw `.torrent` file contents (a bencoded dictionary)
 * @returns The raw bytes of the top-level `info` value
 * @throws ParseError if the data is not a dict or has no `info` key
 */
export function extractInfoDictBytes(data: Uint8Array): Uint8Array {
  const state: DecoderState = { data, pos: 0 };

  if (state.pos >= state.data.length || byteAt(state) !== BYTE_D) {
    throw new ParseError("Torrent data is not a bencode dictionary");
  }

  // Skip 'd'.
  state.pos++;

  while (state.pos < state.data.length) {
    if (byteAt(state) === BYTE_E) {
      // 'e' — end of dict, no `info` key found.
      break;
    }

    // Key is a byte string (decoded as UTF-8, like decodeDict).
    const key = decodeByteString(state, "utf-8");
    if (typeof key !== "string") {
      throw new ParseError("Dictionary key must be a string");
    }

    // The value's raw bytes begin here.
    const valueStart = state.pos;
    // Advance the cursor past the value in lossless "binary" mode (the decoded
    // value is discarded — only the resulting offset is used).
    decodeValue(state, "binary");
    const valueEnd = state.pos;

    if (key === "info") {
      return data.slice(valueStart, valueEnd);
    }
  }

  throw new ParseError("Torrent missing required 'info' dictionary");
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
 * @param hex - Hex string to convert (even number of hex digits)
 * @returns Byte array
 * @throws ParseError if the hex string has an odd length or a non-hex digit
 */
export function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) {
    throw new ParseError(`Hex string must have an even length, got: ${hex.length}`);
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    const byte = parseInt(hex.substring(i, i + 2), 16);
    if (Number.isNaN(byte)) {
      throw new ParseError(
        `Invalid hex digit at position ${i}: "${hex.substring(i, i + 2)}"`,
      );
    }
    bytes[i / 2] = byte;
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
  // Copy into a fresh ArrayBuffer-backed view. `Uint8Array` widens to
  // `Uint8Array<ArrayBufferLike>` under TS 5.7, which is not assignable to
  // `BufferSource` (the backing buffer could in theory be a SharedArrayBuffer);
  // `new Uint8Array(data)` is `Uint8Array<ArrayBuffer>` and binary-identical.
  const input = new Uint8Array(data);
  const hashBuffer = await crypto.subtle.digest("SHA-1", input);
  const hashBytes = new Uint8Array(hashBuffer);
  return bytesToHex(hashBytes);
}
