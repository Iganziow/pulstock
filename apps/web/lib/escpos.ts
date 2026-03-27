/**
 * ESC/POS command encoder for thermal printers.
 * Generates Uint8Array with standard ESC/POS byte sequences.
 */

export const COLS_58MM = 32;
export const COLS_80MM = 48;

// CP437 / Latin-1 mapping for Spanish characters
const CHAR_MAP: Record<string, number> = {
  "ñ": 0xa4, "Ñ": 0xa5,
  "á": 0xa0, "é": 0x82, "í": 0xa1, "ó": 0xa2, "ú": 0xa3,
  "Á": 0xb5, "É": 0x90, "Í": 0xd6, "Ó": 0xe0, "Ú": 0xe9,
  "ü": 0x81, "Ü": 0x9a,
  "¿": 0xa8, "¡": 0xad,
  "°": 0xf8, "€": 0xee,
};

function encodeText(s: string): number[] {
  const bytes: number[] = [];
  for (const ch of s) {
    if (CHAR_MAP[ch] !== undefined) {
      bytes.push(CHAR_MAP[ch]);
    } else {
      const code = ch.charCodeAt(0);
      bytes.push(code > 127 ? 0x3f : code); // '?' for unmapped
    }
  }
  return bytes;
}

export class EscPos {
  private buf: number[] = [];

  /** ESC @ — Initialize printer */
  init(): this {
    this.buf.push(0x1b, 0x40);
    return this;
  }

  /** Raw text (encoded to CP437) */
  text(s: string): this {
    this.buf.push(...encodeText(s));
    return this;
  }

  /** Newline */
  nl(): this {
    this.buf.push(0x0a);
    return this;
  }

  /** ESC E n — Bold on/off */
  bold(on: boolean): this {
    this.buf.push(0x1b, 0x45, on ? 1 : 0);
    return this;
  }

  /** ESC a n — Alignment: 0=left, 1=center, 2=right */
  align(a: "left" | "center" | "right"): this {
    const n = a === "center" ? 1 : a === "right" ? 2 : 0;
    this.buf.push(0x1b, 0x61, n);
    return this;
  }

  /** GS ! n — Character size (width 1-2, height 1-2) */
  fontSize(w: 1 | 2, h: 1 | 2): this {
    const n = ((w - 1) << 4) | (h - 1);
    this.buf.push(0x1d, 0x21, n);
    return this;
  }

  /** Print a separator line */
  separator(char = "-", cols = COLS_80MM): this {
    this.buf.push(...encodeText(char.repeat(cols)));
    this.buf.push(0x0a);
    return this;
  }

  /** Print a double separator line */
  doubleSeparator(cols = COLS_80MM): this {
    return this.separator("=", cols);
  }

  /** Print left-justified text + right-justified text on the same line */
  textLine(left: string, right: string, cols = COLS_80MM): this {
    const gap = cols - left.length - right.length;
    const line = gap > 0 ? left + " ".repeat(gap) + right : (left + " " + right).slice(0, cols);
    this.buf.push(...encodeText(line));
    this.buf.push(0x0a);
    return this;
  }

  /** Print centered text */
  centerText(s: string, cols = COLS_80MM): this {
    const pad = Math.max(0, Math.floor((cols - s.length) / 2));
    this.buf.push(...encodeText(" ".repeat(pad) + s));
    this.buf.push(0x0a);
    return this;
  }

  /** ESC d n — Feed n lines */
  feed(n = 1): this {
    this.buf.push(0x1b, 0x64, n);
    return this;
  }

  /** GS V 66 3 — Partial cut */
  cut(): this {
    this.buf.push(0x1d, 0x56, 0x42, 0x03);
    return this;
  }

  /** Append raw bytes */
  raw(bytes: number[]): this {
    this.buf.push(...bytes);
    return this;
  }

  /** Build final Uint8Array */
  build(): Uint8Array {
    return new Uint8Array(this.buf);
  }
}
