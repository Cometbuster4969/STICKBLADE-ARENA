import Link from "next/link";
import SiteNav, { SiteFooter } from "@/components/SiteNav";

export const metadata = {
  title: "Trust & data handling — STICKBLADE ARENA",
  description:
    "What Stickblade Arena collects, how BYOK keys are handled, how long " +
    "match data is kept, and how to request deletion.",
};

/**
 * Trust page (action-plan §23).
 *
 * We ask visitors to paste an API key into a browser form and to vote on
 * matches. Both deserve a plain-language explanation of what happens to
 * that data, plus a way to reach a human.
 */
const SECTIONS = [
  {
    h: "What is collected",
    rows: [
      ["Match configuration", "The two model ids, weapon, arena, sharp "
        + "zones, control mode, match length, seed and fallback policy you "
        + "choose — stored with the match so results can be audited."],
      ["Match results", "Winner, method, turn count, per-turn damage events, "
        + "the replay frames, and per-turn latency / fallback / "
        + "invalid-action counters."],
      ["Votes", "Your tactical vote (the one that moves ratings) and, if you "
        + "fill them in, the optional execution / entertainment / deserved "
        + "axes and a 1–5 confidence rating. Anonymous — no account, no "
        + "user id."],
      ["Aggregate analytics", "Page views and referrers (Vercel Analytics, "
        + "privacy-friendly, no cross-site cookies)."],
      ["Server logs", "The hosting provider records IP, timestamp, path and "
        + "status for abuse prevention and rate limiting."],
    ],
  },
  {
    h: "What is NOT collected",
    rows: [
      ["No accounts", "There is no signup, no email list on the arena "
        + "itself, and no advertising or cross-site tracking."],
      ["No BYOK key storage", "A key pasted into the BYOK panel is sent "
        + "with one match request and never written to the database."],
      ["No prompt echo", "Your key is never echoed back in any API "
        + "response, replay file or log message."],
      ["No PII in the dataset", "Public exports contain model ids, configs, "
        + "timings and outcomes only — no IPs, no user ids, no keys."],
    ],
  },
];

export default function TrustPage() {

  return (
    <>
      <SiteNav />
    <div className="container">
      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Trust, privacy &amp; data handling
        </span>
        <p style={{ color: "var(--text-2)", marginTop: 10, maxWidth: "78ch",
                    lineHeight: 1.7 }}>
          Stickblade Arena is an open benchmark, so the data-handling story
          has to be as inspectable as the physics. This page states plainly
          what is stored, what is not, and how to get your data removed.
          The code is public:{" "}
          <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA"
             target="_blank" rel="noreferrer"
             style={{ color: "var(--gold)" }}>
            github.com/Cometbuster4969/STICKBLADE-ARENA
          </a>.
        </p>
      </div>

      {SECTIONS.map((sec) => (
        <div className="panel" key={sec.h}>
          <span className="panel-title">
            <span className="tick" /> {sec.h}
          </span>
          <table className="prov-table" style={{ marginTop: 10 }}>
            <tbody>
              {sec.rows.map(([k, v]) => (
                <tr key={k}>
                  <td style={{ width: "22%", color: "var(--text)",
                               fontWeight: 700 }}>{k}</td>
                  <td style={{ color: "var(--dim)", fontFamily: "inherit",
                               fontSize: 13, lineHeight: 1.6 }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> BYOK (bring your own key)
        </span>
        <ol style={{ marginTop: 10, paddingLeft: 20, color: "var(--dim)",
                     fontSize: 13, lineHeight: 1.8 }}>
          <li>Your key lives in this browser&apos;s localStorage only, until
            you remove it.</li>
          <li>When BYOK is enabled it is sent with one{" "}
            <code>POST /api/match</code> request over HTTPS.</li>
          <li>The backend keeps it in memory for the duration of that match
            and discards it when the simulation ends — it is never written
            to the database, the replay file, or a log line.</li>
          <li>Error messages are scrubbed of URLs, bearer tokens and
            <code> sk-*</code> strings before they reach you.</li>
          <li>You can delete it at any time with “remove key” in the setup
            panel. Clearing site data also removes it.</li>
        </ol>
      </div>

      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Retention, deletion &amp; contact
        </span>
        <table className="prov-table" style={{ marginTop: 10 }}>
          <tbody>
            <tr>
              <td style={{ width: "22%" }}>Match rows</td>
              <td>Kept indefinitely as benchmark data — a published result
                has to stay reproducible. They contain no personal data.</td>
            </tr>
            <tr>
              <td>Votes</td>
              <td>Anonymous and attached only to a match id. There is no
                way to link a vote to a person, so a deletion request
                cannot be scoped to “my votes”.</td>
            </tr>
            <tr>
              <td>Replay files</td>
              <td>Kept with the match; frames contain only physics state.</td>
            </tr>
            <tr>
              <td>Server logs</td>
              <td>Retained by the hosting provider on its own schedule.</td>
            </tr>
            <tr>
              <td>Deletion / questions</td>
              <td>Open a GitHub issue or email the maintainer via the GitHub
                profile linked in the footer. Because no accounts exist,
                “my data” means data you can identify — point us at the
                match id and it goes.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Known limitations
        </span>
        <ul style={{ marginTop: 10, paddingLeft: 20, color: "var(--dim)",
                     fontSize: 13, lineHeight: 1.8 }}>
          <li>Matches depend on third-party model providers; latency and
            rate limits affect outcomes. We publish latency, fallback and
            invalid-action rates per match so you can judge for yourself.</li>
          <li>Ratings are segmented per configuration cell and provisional
            below 10 matches — a leaderboard number is not a general
            intelligence ranking.</li>
          <li>Human tactical votes are the ranked signal. Entertainment and
            execution votes are collected but never ranked.</li>
          <li>This is a solo-run research project on free tiers. There is no
            SLA and no paid support.</li>
        </ul>
        <p style={{ marginTop: 12, fontSize: 13 }}>
          <Link href="/status" style={{ color: "var(--gold)" }}>
            Live service status →
          </Link>
        </p>
      </div>
    </div>
      <SiteFooter />
    </>
  );
}
