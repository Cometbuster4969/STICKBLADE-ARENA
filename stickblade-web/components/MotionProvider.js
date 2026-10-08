"use client";
/**
 * Bridges the site's accessibility preferences into framer-motion.
 *
 * lib/prefs.js already writes data-motion="reduced" on <html>, which is all
 * plain CSS needs. framer-motion animates in JS though, so a "Reduced motion"
 * toggle would otherwise leave every scroll reveal and spring still moving —
 * exactly the vestibular problem the toggle exists to solve.
 *
 * reducedMotion="always" makes framer-motion drop transform/layout animations
 * and keep only opacity, which is the behaviour we want when the visitor has
 * asked for calm. "user" defers to the OS preference when the site has no
 * explicit choice recorded.
 */
import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { readPrefs, applyPrefs, subscribePrefs } from "@/lib/prefs";

export default function MotionProvider({ children }) {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    // Apply the stored/OS-derived prefs before anything animates, so the CSS
    // data-* switches and the JS ones can never disagree on first paint. This
    // used to happen inside A11yControls, which is now behind a popover.
    const initial = readPrefs();
    applyPrefs(initial);
    const sync = (p) => setReduced((p || readPrefs()).motion === "reduced");
    sync(initial);
    const unsub = subscribePrefs(sync);
    // Also follow the live OS setting if the user never chose explicitly.
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const onMq = () => sync();
    mq?.addEventListener?.("change", onMq);
    return () => { unsub(); mq?.removeEventListener?.("change", onMq); };
  }, []);

  return (
    <MotionConfig reducedMotion={reduced ? "always" : "user"}>
      {children}
    </MotionConfig>
  );
}
