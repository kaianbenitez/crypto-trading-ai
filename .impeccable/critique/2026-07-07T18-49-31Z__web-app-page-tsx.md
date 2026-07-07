---
target: web/app/page.tsx (dashboard)
total_score: 24
p0_count: 2
p1_count: 2
timestamp: 2026-07-07T18-49-31Z
slug: web-app-page-tsx
---
Method: dual-agent (A: general-purpose design review · B: detector + browser evidence attempt)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Stat row uses Skeleton loading; Open Positions section uses plain "Loading positions..." text — inconsistent |
| 2 | Match System / Real World | 3 | Plain-language labels are good; "ROI", "risk n/a", "size ×0.85" still leak jargon |
| 3 | User Control and Freedom | 3 | Kill switch has confirm/cancel/Escape; no way to collapse a card's reasoning block if unwanted |
| 4 | Consistency and Standards | 2 | Two structurally different open-position layouts (`DetailedOpenPosition` vs `OpenPosition`) render for the same concept depending on backend data availability |
| 5 | Error Prevention | 3 | Halt requires confirmation; solid |
| 6 | Recognition Rather Than Recall | 2 | Red/green/amber reused across side, PnL, risk badges, halted state, regime, sentiment — meaning re-derived per context |
| 7 | Flexibility and Efficiency | 2 | No density toggle, no collapse for Coin Watch/Closed Trades, no filters |
| 8 | Aesthetic and Minimalist Design | 1 | Every open-position card is stuffed to capacity — this is the core complaint |
| 9 | Error Recovery | 3 | Retry button on API error works cleanly |
| 10 | Help and Documentation | 2 | No legend for SL/E/TP dots or "size ×"; acceptable for a solo user but hurts a first-timer |
| **Total** | | **24/40** | **Acceptable — needs real trimming, foundation is solid** |

## Anti-Patterns Verdict

**LLM assessment**: Not AI-slop at the infrastructure level — the token system, spacing scale, and Card/Badge/Button/StatCard shells are disciplined, real design system work, not generic template output. The failure is different: it reads as *assembled feature-by-feature* rather than *designed as one glance*. Every open-position card independently tries to be complete (P&L + price + range bar + 3 price tiles + risk%/qty + strategy/regime text + thesis + why-accepted + weakness + invalidation + past-context), so the "monitoring surface" reads like a spec sheet. That's exactly your complaint: too much on screen, low signal-to-noise per card.

**Deterministic scan**: `detect.mjs --json web/app/page.tsx` returned zero findings (clean exit). The automated scanner catches known AI-slop *patterns* (gradient text, side-stripe borders, eyebrow scaffolding, etc.) — this page has none of those. The problem here is architectural/informational density, not a pattern the static detector is built to catch. No false positives to report since there were no findings.

**Visual overlays**: Not available this session. The Turbopack dev server panicked with an OS-level resource error (`Insufficient system resources exist to complete the requested service, os error 1450`) trying to compile `globals.css` — a known sandbox memory ceiling, not a bug in your code. Browser-side visual confirmation wasn't possible; this critique is based on source reading only for the visual portion, which is why the findings below are framed as "here's what the code renders," not "here's what I saw in the browser."

## Overall Impression

The foundation (tokens, kill-switch UX, component shells) is genuinely good and doesn't need a redesign. The problem is entirely in the open-position card: it currently shows ~9 distinct pieces of information at once for a task you described as "surveillance, not analysis" — glance, not read. The single biggest win available is collapsing the reasoning narrative (thesis/why-accepted/weakness/invalidation/past-context) behind a default-closed disclosure, and merging the two different open-position card components into one so the "normal" case isn't also the noisiest one.

## What's Working

- **Token system & shared components** (spacing, type scale, radius, motion, `Card`/`Badge`/`Button`/`StatCard`) — real, reusable infrastructure, not templated slop.
- **Kill switch UX** — confirm + cancel + Escape-to-cancel + focus management + 44px touch target. This is the standout of the page and matches your "instant control" principle exactly.
- **Existing editorial instincts already in the code** — `specificReasoning()`, `noteworthyExitReason()`, `OBVIOUS_EXIT_REASONS` show you've already started cutting redundant text per-string. This just needs to go further and apply structurally (which fields show by default), not just which words show.

## Priority Issues

**[P0] The reasoning block is unbounded and always-on.**
*What*: `DetailedOpenPosition` (page.tsx:187-216) permanently renders Thesis, "Why accepted," Weakness, Invalidation, and Past Context on every open position, every 15s refresh.
*Why it matters*: This is the direct cause of "too much info on my screen." Of those five fields, only Weakness is genuinely action-relevant at a glance (it's a live warning); the rest is after-the-fact narrative you'd only want on demand.
*Fix*: Default-show only P&L / price / range bar / risk footer. Show Weakness inline as a small warning chip if present. Collapse Thesis/why-accepted/invalidation/past-context behind a "Reasoning ▾" disclosure per card.
*Suggested command*: `/impeccable distill` (strip to essence) or `/impeccable layout` (restructure the card).

**[P0] Two different open-position card components for the same concept.**
*What*: `DetailedOpenPosition` and `OpenPosition` (page.tsx:113-283) render entirely different field sets/order depending on whether `positionDetails` loaded from the API.
*Why it matters*: Doubles the visual vocabulary you have to learn, and the "detailed" version — the common case — is also the noisiest one. Also a Nielsen consistency violation.
*Fix*: Merge into one component with one canonical field order. If `live`/`payload`/reasoning data is missing, degrade gracefully within the same layout instead of swapping to a structurally different card.
*Suggested command*: `/impeccable layout`

**[P1] "X% risked · qty Y" footer duplicated on every card, open and closed.**
*What*: Appears on `DetailedOpenPosition`, `OpenPosition`, and `TradeRow` (page.tsx:184, 268, 336).
*Why it matters*: Not actionable at a glance; the bot already sized the position, this is a fact for the journal, not the dashboard. On the compact closed-trade tile it directly competes with the PnL% for attention.
*Fix*: Drop from `TradeRow` entirely (journal page already has it in detail). Move to a hover tooltip on the open-position cards.
*Suggested command*: `/impeccable distill`

**[P1] SL/Entry/TP shown twice — as dot markers on the range bar AND as three separate labeled tiles.**
*What*: `PnlBar` dots (page.tsx:83-96) and the 3-tile grid (page.tsx:170-181) encode the identical three numbers.
*Why it matters*: Pure duplication inflates card height and reading time for zero new information.
*Fix*: Keep the bar as primary source of truth; drop the tile grid, or fold SL/Entry/TP into the single-line caption pattern `OpenPosition` already uses (page.tsx:248-252) and delete the tile grid from `DetailedOpenPosition`.
*Suggested command*: `/impeccable distill`

**[P2] "Coin Watch" (daily-refresh) competes for the same visual weight as live 15s data.**
*What*: Full card grid of sentiment/summary/watch-range per coin sits permanently below live positions at parity with real-time cards (page.tsx:578-591).
*Why it matters*: A once-a-day artifact shouldn't occupy prime real estate at the same visual weight as live data — it dilutes the "is the bot healthy right now" hierarchy that's supposed to be answered first.
*Fix*: Collapse to a compact single-row ticker by default; link out to the dedicated `/coins` page for full digest cards.
*Suggested command*: `/impeccable layout`

## Persona Red Flags

**Alex (Power User)**: Has to scroll past a 5-part reasoning essay per open position just to answer "is this trade fine" — directly against the stated surveillance-not-analysis job. The two-component fork means Alex's card layout changes shape depending on backend data timing, which reads as a bug even though it isn't. No density/collapse control anywhere to say "just show me numbers."

**Sam (Accessibility-Dependent User)**: SL/Entry/TP dot markers on `PnlBar` are color-only with the label available solely via a hover `title` — not screen-reader-friendly, invisible without hover, unusable on touch without tap-and-hold. `--text-2xs` (11px) is used heavily for content that matters (Weakness, Invalidation, risk%) on a screen meant to be read fast; there's no way to bump density/type scale.

## Minor Observations

- Loading-state pattern is inconsistent: stat row uses `Skeleton`, Open Positions section uses plain "Loading positions..." text.
- The "▐▐ TRADING HALTED" banner uses raw block characters instead of an actual icon, inconsistent with the Phosphor icon vocabulary used everywhere else.
- `REGIME_META`, `STRATEGY_LABEL`, `TRADE_REGIME_LABEL` are three separate lookup tables for what's conceptually one taxonomy (market condition) — worth consolidating.
- Regime/strategy context is shown at 3 altitudes (macro stat tile, per-trade regime text, per-trade strategy label) without being unified — user re-derives the same concept three times per scan.

## Questions to Consider

- If Weakness is the only genuinely action-relevant field in the reasoning block, why does it render at the same size/weight as Past Context, which is pure narrative?
- Is Coin Watch actually a dashboard-tier concern, or a research page that got pinned to the dashboard out of convenience?
- Did the two open-position components diverge on purpose, or did nobody revisit the simple version after the detailed one shipped?
