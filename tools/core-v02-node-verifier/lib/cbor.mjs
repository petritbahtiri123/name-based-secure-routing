import { TextDecoder, TextEncoder } from "node:util";

export const DEFAULT_LIMITS = Object.freeze({
  maxTotalBytes: 65_536,
  maxDepth: 16,
  maxArrayItems: 256,
  maxMapPairs: 128,
  maxTextBytes: 4_096,
  maxByteStringBytes: 32_768,
});

export class CborError extends Error {
  constructor(kind, message) {
    super(message);
    this.name = "CborError";
    this.kind = kind;
  }
}

export class CborTag {
  constructor(tag, value) {
    this.tag = tag;
    this.value = value;
    Object.freeze(this);
  }
}

const UTF8_DECODER = new TextDecoder("utf-8", { fatal: true });
const UTF8_ENCODER = new TextEncoder();
const WIDTHS = new Map([
  [24, 1],
  [25, 2],
  [26, 4],
  [27, 8],
]);
const MINIMUMS = new Map([
  [24, 24n],
  [25, 0x100n],
  [26, 0x10000n],
  [27, 0x100000000n],
]);

function profile(message = "unsupported or non-deterministic CBOR") {
  throw new CborError("profile", message);
}

function capacity(message = "CBOR resource limit exceeded") {
  throw new CborError("capacity", message);
}

function limitsFrom(options) {
  const limits = { ...DEFAULT_LIMITS, ...(options?.limits ?? {}) };
  for (const [name, value] of Object.entries(limits)) {
    if (!Number.isSafeInteger(value) || value < 0) {
      profile(`invalid CBOR limit: ${name}`);
    }
  }
  return limits;
}

function asNumberOrBigInt(value) {
  return value <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(value) : value;
}

class Decoder {
  constructor(data, limits, allowTag18) {
    this.data = data;
    this.limits = limits;
    this.allowTag18 = allowTag18;
    this.offset = 0;
  }

  take(count) {
    const end = this.offset + count;
    if (!Number.isSafeInteger(count) || count < 0 || end > this.data.length) {
      profile("truncated CBOR");
    }
    const value = this.data.subarray(this.offset, end);
    this.offset = end;
    return value;
  }

  argument(additional) {
    if (additional < 24) {
      return BigInt(additional);
    }
    const width = WIDTHS.get(additional);
    if (width === undefined) {
      profile("indefinite or reserved CBOR argument");
    }
    const bytes = this.take(width);
    let value = 0n;
    for (const byte of bytes) {
      value = (value << 8n) | BigInt(byte);
    }
    if (value < MINIMUMS.get(additional)) {
      profile("non-preferred CBOR argument");
    }
    return value;
  }

  count(value, limit) {
    if (value > BigInt(limit) || value > BigInt(Number.MAX_SAFE_INTEGER)) {
      capacity();
    }
    return Number(value);
  }

  item(depth) {
    if (depth > this.limits.maxDepth) {
      capacity();
    }
    const initial = this.take(1)[0];
    const major = initial >> 5;
    const additional = initial & 0x1f;

    if (major === 0) {
      return asNumberOrBigInt(this.argument(additional));
    }
    if (major === 1) {
      const argument = this.argument(additional);
      const value = -1n - argument;
      return value >= BigInt(Number.MIN_SAFE_INTEGER) ? Number(value) : value;
    }
    if (major === 2 || major === 3) {
      const lengthLimit = major === 2
        ? this.limits.maxByteStringBytes
        : this.limits.maxTextBytes;
      const length = this.count(this.argument(additional), lengthLimit);
      const content = this.take(length);
      if (major === 2) {
        return Buffer.from(content);
      }
      try {
        return UTF8_DECODER.decode(content);
      } catch {
        profile("invalid UTF-8 text string");
      }
    }
    if (major === 4) {
      const count = this.count(this.argument(additional), this.limits.maxArrayItems);
      const result = [];
      for (let index = 0; index < count; index += 1) {
        result.push(this.item(depth + 1));
      }
      return result;
    }
    if (major === 5) {
      const count = this.count(this.argument(additional), this.limits.maxMapPairs);
      const result = new Map();
      let previousKey = null;
      for (let index = 0; index < count; index += 1) {
        const keyStart = this.offset;
        const key = this.item(depth + 1);
        const encodedKey = this.data.subarray(keyStart, this.offset);
        if (previousKey !== null && Buffer.compare(previousKey, encodedKey) >= 0) {
          profile("duplicate or incorrectly ordered map key");
        }
        previousKey = encodedKey;
        result.set(key, this.item(depth + 1));
      }
      return result;
    }
    if (major === 6) {
      const tag = this.argument(additional);
      if (!this.allowTag18 || tag !== 18n) {
        profile("unsupported CBOR tag");
      }
      return new CborTag(18, this.item(depth + 1));
    }
    if (major === 7 && additional === 20) {
      return false;
    }
    if (major === 7 && additional === 21) {
      return true;
    }
    if (major === 7 && additional === 22) {
      return null;
    }
    profile("unsupported CBOR simple value or float");
  }
}

function encodeHead(major, argument) {
  if (argument < 0n || argument > 0xffffffffffffffffn) {
    profile("integer outside the supported uint64 range");
  }
  const initial = major << 5;
  if (argument < 24n) {
    return Buffer.from([initial | Number(argument)]);
  }
  for (const [additional, width] of WIDTHS) {
    const maximum = (1n << BigInt(width * 8)) - 1n;
    if (argument <= maximum) {
      const result = Buffer.alloc(1 + width);
      result[0] = initial | additional;
      let remaining = argument;
      for (let index = width; index > 0; index -= 1) {
        result[index] = Number(remaining & 0xffn);
        remaining >>= 8n;
      }
      return result;
    }
  }
  profile("integer outside the supported uint64 range");
}

function checked(parts, budget) {
  const length = parts.reduce((total, part) => total + part.length, 0);
  if (length > budget) {
    capacity();
  }
  return Buffer.concat(parts, length);
}

function encodeValue(value, limits, allowTag18, depth, active, budget) {
  if (depth > limits.maxDepth) {
    capacity();
  }
  if (value === null) {
    return checked([Buffer.from([0xf6])], budget);
  }
  if (value === false) {
    return checked([Buffer.from([0xf4])], budget);
  }
  if (value === true) {
    return checked([Buffer.from([0xf5])], budget);
  }
  if (typeof value === "number" || typeof value === "bigint") {
    if (typeof value === "number" && !Number.isSafeInteger(value)) {
      profile("unsupported numeric value");
    }
    const integer = BigInt(value);
    const encoded = integer >= 0n
      ? encodeHead(0, integer)
      : encodeHead(1, -1n - integer);
    return checked([encoded], budget);
  }
  if (Buffer.isBuffer(value)) {
    if (value.length > limits.maxByteStringBytes) {
      capacity();
    }
    return checked([encodeHead(2, BigInt(value.length)), value], budget);
  }
  if (typeof value === "string") {
    if (!value.isWellFormed()) {
      profile("invalid Unicode string");
    }
    const encoded = Buffer.from(UTF8_ENCODER.encode(value));
    if (encoded.length > limits.maxTextBytes) {
      capacity();
    }
    return checked([encodeHead(3, BigInt(encoded.length)), encoded], budget);
  }
  if (value instanceof CborTag) {
    if (!allowTag18 || value.tag !== 18) {
      profile("unsupported CBOR tag");
    }
    if (active.has(value)) {
      profile("cyclic CBOR value");
    }
    active.add(value);
    try {
      const head = encodeHead(6, 18n);
      const item = encodeValue(
        value.value,
        limits,
        allowTag18,
        depth + 1,
        active,
        budget - head.length,
      );
      return checked([head, item], budget);
    } finally {
      active.delete(value);
    }
  }
  if (Array.isArray(value)) {
    if (value.length > limits.maxArrayItems) {
      capacity();
    }
    if (active.has(value)) {
      profile("cyclic CBOR value");
    }
    active.add(value);
    try {
      const parts = [encodeHead(4, BigInt(value.length))];
      let remaining = budget - parts[0].length;
      for (const item of value) {
        const encoded = encodeValue(item, limits, allowTag18, depth + 1, active, remaining);
        parts.push(encoded);
        remaining -= encoded.length;
      }
      return checked(parts, budget);
    } finally {
      active.delete(value);
    }
  }
  if (value instanceof Map) {
    if (value.size > limits.maxMapPairs) {
      capacity();
    }
    if (active.has(value)) {
      profile("cyclic CBOR value");
    }
    active.add(value);
    try {
      const head = encodeHead(5, BigInt(value.size));
      const entries = [];
      for (const [key, item] of value) {
        entries.push([
          encodeValue(key, limits, allowTag18, depth + 1, active, budget - head.length),
          item,
        ]);
      }
      entries.sort(([left], [right]) => Buffer.compare(left, right));
      for (let index = 1; index < entries.length; index += 1) {
        if (Buffer.compare(entries[index - 1][0], entries[index][0]) === 0) {
          profile("duplicate deterministic map key");
        }
      }
      const parts = [head];
      let remaining = budget - head.length;
      for (const [key, item] of entries) {
        if (key.length > remaining) {
          capacity();
        }
        parts.push(key);
        remaining -= key.length;
        const encoded = encodeValue(item, limits, allowTag18, depth + 1, active, remaining);
        parts.push(encoded);
        remaining -= encoded.length;
      }
      return checked(parts, budget);
    } finally {
      active.delete(value);
    }
  }
  profile("unsupported CBOR value");
}

export function encodeDeterministic(value, options = {}) {
  const limits = limitsFrom(options);
  return encodeValue(
    value,
    limits,
    options.allowTag18 === true,
    1,
    new Set(),
    limits.maxTotalBytes,
  );
}

export function decodeDeterministic(data, options = {}) {
  if (!Buffer.isBuffer(data)) {
    profile("CBOR input must be a Buffer");
  }
  const limits = limitsFrom(options);
  if (data.length > limits.maxTotalBytes) {
    capacity();
  }
  const decoder = new Decoder(data, limits, options.allowTag18 === true);
  const value = decoder.item(1);
  if (decoder.offset !== data.length) {
    profile("trailing CBOR bytes");
  }
  if (!encodeDeterministic(value, { limits, allowTag18: options.allowTag18 === true }).equals(data)) {
    profile("CBOR does not re-encode deterministically");
  }
  return value;
}
