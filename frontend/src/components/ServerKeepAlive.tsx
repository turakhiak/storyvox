"use client";

/**
 * Pings the backend every 10 minutes while the tab is open.
 * Render's free tier spins down after 15 min of inactivity — this prevents
 * cold starts for users who keep the app open in a tab.
 * Renders nothing; pure side-effect component.
 */

import { useEffect } from "react";
import { pingServer } from "@/lib/api";

const PING_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

export default function ServerKeepAlive() {
  useEffect(() => {
    // Ping once on mount (handles the case where user opens a book page directly)
    pingServer().catch(() => {});

    const id = setInterval(() => {
      pingServer().catch(() => {});
    }, PING_INTERVAL_MS);

    return () => clearInterval(id);
  }, []);

  return null;
}
