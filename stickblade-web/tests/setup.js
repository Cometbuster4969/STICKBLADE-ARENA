import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * jsdom keeps a single document and localStorage for the whole file, so
 * without this a component mounted in one test stays in the DOM for the
 * next one and `getByRole` starts matching twice. localStorage is cleared
 * too: VotePanel persists the expert tier there, and a leaked "expert"
 * value would silently change the payload the following test asserts on.
 */
afterEach(() => {
  cleanup();
  try {
    localStorage.clear();
  } catch {
    /* jsdom always provides localStorage; guard for odd environments */
  }
});
