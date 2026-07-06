"use client";

import { useEffect, useState } from "react";
import AuthGate from "../components/AuthGate";
import Sidebar from "../components/Sidebar";
import { api } from "@/lib/api";

// Minimal inline-markdown renderer for **bold** — good enough for our changelog's style.
function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>
  );
}

function renderMarkdown(markdown: string) {
  const lines = markdown.split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={blocks.length} style={{ margin: "0 0 14px", paddingLeft: 20, color: "var(--text)", fontSize: 13, lineHeight: 1.7 }}>
        {listItems.map((item, i) => <li key={i} style={{ marginBottom: 6 }}>{inline(item)}</li>)}
      </ul>
    );
    listItems = [];
  }

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("## ")) {
      flushList();
      blocks.push(<h2 key={blocks.length} style={{ fontSize: 15, fontWeight: 700, margin: "22px 0 8px" }}>{line.slice(3)}</h2>);
    } else if (line.startsWith("# ")) {
      flushList();
      blocks.push(<h1 key={blocks.length} style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px" }}>{line.slice(2)}</h1>);
    } else if (line.trim().startsWith("- ")) {
      listItems.push(line.trim().slice(2));
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={blocks.length} style={{ color: "var(--muted)", fontSize: 12.5, margin: "0 0 12px" }}>{inline(line)}</p>);
    }
  }
  flushList();
  return blocks;
}

function ChangelogContent() {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.changelog()
      .then(c => setMarkdown(c.markdown))
      .catch(() => setError("Could not load the changelog"));
  }, []);

  return (
    <div className="app-shell" style={{ minHeight: "100dvh", background: "var(--bg)", color: "var(--text)", display: "flex" }}>
      <Sidebar />
      <main className="page-main" style={{ flex: 1, minWidth: 0, maxWidth: 760, margin: "0 auto" }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Changelog</h1>
          <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0 0" }}>What's changed in the trading bot, most recent first.</p>
        </div>

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "16px 20px" }}>
          {markdown === null && !error ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</div>
          ) : (
            renderMarkdown(markdown || "")
          )}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <ChangelogContent />
    </AuthGate>
  );
}
