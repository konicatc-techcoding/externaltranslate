import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest only auto-cleans when `globals` is on; without this, rendered trees
// pile up and queries start matching elements from earlier tests.
afterEach(() => {
  cleanup();
});
