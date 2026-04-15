/**
 * Thin wrapper around console that silences logs in production.
 * Use this instead of `console.error` / `console.log` everywhere in client code
 * to avoid leaking internals to end users' browser consoles.
 */

const IS_DEV = process.env.NODE_ENV !== "production";

export const logger = {
  error: (...args: unknown[]) => {
    if (IS_DEV) {
      // eslint-disable-next-line no-console
      console.error(...args);
    }
  },
  warn: (...args: unknown[]) => {
    if (IS_DEV) {
      // eslint-disable-next-line no-console
      console.warn(...args);
    }
  },
  log: (...args: unknown[]) => {
    if (IS_DEV) {
      // eslint-disable-next-line no-console
      console.log(...args);
    }
  },
};
