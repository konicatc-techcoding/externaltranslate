import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest only auto-cleans when `globals` is on; without this, rendered trees
// pile up and queries start matching elements from earlier tests.
afterEach(() => {
  cleanup();
});

// jsdom implements <dialog> as an element but not its modal behaviour. The
// confirmation dialog uses `showModal` for the focus trap and Esc handling a
// real browser gives for free, so the shim is here rather than the product
// being written down to what jsdom supports.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal ??= function showModal(
    this: HTMLDialogElement,
  ) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function close(
    this: HTMLDialogElement,
  ) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}
