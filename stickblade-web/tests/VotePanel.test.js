/* eslint-disable no-undef */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";

import VotePanel from "@/components/VotePanel";

/**
 * First frontend test tier for the arena.
 *
 * These exist because the blind-vote guarantee was previously enforced only
 * on the server: tests/test_blind_identity.py proves the *payload* carries no
 * model identity, but nothing proved the *UI* does not invent one — e.g. by
 * rendering a model name in an aria-label, a title attribute or a hidden
 * span. That is a leak path the backend tests structurally cannot see.
 *
 * Scope is deliberately the voting surface, not the whole app: it is the one
 * screen where a leak actually costs something.
 */

const tacticalGroup = () => within(screen.getByRole("group", { name: "Tactical vote" }));

function renderPanel(props = {}) {
  const onVote = vi.fn().mockResolvedValue(undefined);
  return { onVote, ...render(<VotePanel onVote={onVote} {...props} />) };
}

describe("VotePanel — blind voting surface", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("never renders a model identity anywhere in the DOM", () => {
    const { container } = renderPanel();

    // The panel is only ever given canvas-side sides, so any of these
    // appearing means something upstream (or a future prop) leaked one.
    expect(container.textContent).not.toMatch(
      /gpt|claude|gemini|llama|qwen|mistral|deepseek|mock:|bot:pro|bot:greedy/i);

    // Same check over the attributes a sighted user never reads but a
    // screen reader (and any scraper) does.
    const attrs = Array.from(container.querySelectorAll("*")).flatMap((el) =>
      ["aria-label", "title", "alt", "data-model", "data-model-id"]
        .map((a) => el.getAttribute(a)).filter(Boolean));
    for (const value of attrs) {
      expect(value).not.toMatch(/gpt|claude|gemini|llama|qwen|mock:|bot:pro/i);
    }
  });

  it("keeps the vote unreachable until a side is picked", () => {
    const { onVote } = renderPanel();

    expect(screen.queryByRole("button", { name: /Submit vote/ })).toBeNull();

    fireEvent.click(tacticalGroup().getByRole("button", { name: /Fighter A/ }));

    const submit = screen.getByRole("button", { name: /Submit vote/ });
    expect(submit).toBeTruthy();
    expect(submit.disabled).toBe(false);
    expect(onVote).not.toHaveBeenCalled();
  });

  it("submits choice plus an explicit, fully-populated payload", async () => {
    const { onVote } = renderPanel();

    fireEvent.click(tacticalGroup().getByRole("button", { name: /Fighter A/ }));
    fireEvent.click(screen.getByRole("button", { name: /Submit vote/ }));

    await waitFor(() => expect(onVote).toHaveBeenCalledTimes(1));

    // Keys are asserted explicitly: the server has a TypeError fallback that
    // silently drops unknown payload shapes, so a renamed key here would
    // degrade to "tactical vote only" and nobody would notice.
    expect(onVote).toHaveBeenCalledWith("a", {
      execution: null,
      entertainment: null,
      deserved: null,
      confidence: null,
      voter_tier: "casual",
    });
  });

  it("carries optional axes, confidence and the expert tier when filled in", async () => {
    const { onVote } = renderPanel();

    fireEvent.click(tacticalGroup().getByRole("button", { name: /Fighter B/ }));
    fireEvent.click(screen.getByRole("button", { name: /Add detail/ }));

    const executionField = screen.getByText("Executed more cleanly").closest("fieldset");
    fireEvent.click(within(executionField).getByRole("button", { name: "Fighter A" }));

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("checkbox"));

    fireEvent.click(screen.getByRole("button", { name: /Submit vote/ }));

    await waitFor(() => expect(onVote).toHaveBeenCalledTimes(1));
    expect(onVote).toHaveBeenCalledWith("b", {
      execution: "a",
      entertainment: null,
      deserved: null,
      confidence: 4,
      voter_tier: "expert",
    });
  });

  it("disables submission while the reveal request is in flight", () => {
    renderPanel({ disabled: true });

    fireEvent.click(tacticalGroup().getByRole("button", { name: /Fighter A/ }));

    // No double-voting a match: the button is inert while the parent is
    // still awaiting the reveal.
    expect(screen.getByRole("button", { name: /Submit vote/ }).disabled).toBe(true);
  });

  it("exposes the selection as aria-pressed for keyboard/screen-reader users", () => {
    renderPanel();
    const group = tacticalGroup();

    const a = group.getByRole("button", { name: /Fighter A/ });
    const b = group.getByRole("button", { name: /Fighter B/ });

    expect(a.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(a);
    expect(a.getAttribute("aria-pressed")).toBe("true");
    expect(b.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(b);
    expect(b.getAttribute("aria-pressed")).toBe("true");
    expect(a.getAttribute("aria-pressed")).toBe("false");
  });
});
