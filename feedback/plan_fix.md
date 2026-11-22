# Yukti IOCL — `v11` Fix Plan (from `feedback/current_refinements.md`, 22-Nov-2026 09:41–09:50 session)

> **Bottom line:** The live-price DCF flow now works end to end. The session broke down in four other places: (1) the **"why was FY25 profit low?"** explainer, (2) **questions about what is on screen** being sent to Annual Report search, (3) **voice mishearing WACC as "VAT"**, which opened a refinery what-if, and (4) **"10-year total cash flow"** being answered as if the data did not exist. These four are the blockers to fix first.

Source read in full: [current_refinements.md](./current_refinements.md) (551 lines, 19 turns). Every root cause below was traced in code unless it is marked **(hypothesis — verify)**.

---

## 0. Refinement list (prioritised)

| # | Severity | Symptom in transcript (line refs) | Root cause | Primary file(s) |
|---|---|---|---|---|
| R1 | **P0 – Blocking** | "Why was profit exceptionally low in 24-25?" → `PBT changed by -36461.9 crore … PL.REV_OPS had an impact of -20832.8 crore` (L83). The same text was repeated verbatim (L94). A later turn flipped direction to FY25→FY26 (L143, L158). The screen never changed (L97 "which screen are you showing?") | `run_why_turn` builds its narrative from a template that leaks raw `line_code`s and uses Western decimals. The waterfall spec uses `x_key/y_keys` and has no `type: total/delta`, so the renderer does not draw it and the old P&L card stays on screen. The period resolver defaults `fy_to=FY26` when the user says "previous year / 12,962". The bridge is a generic line delta that ignores OMC drivers (GRM $12.05→$4.80, inventory, marketing margins). The good answer existed only in AR RAG (L171) | `backend/app/agents/fin_diagnostics/why.py` (L28–L31, L135–L176), `variance.py`, `brain/pipeline.py:320` |
| R2 | **P0 – Blocking** | "Which screen are you showing?" → AR RAG answered about the *Consolidated* P&L with irrelevant FY18/FY22 chunks (L107). "The screen is not doing any justification" → generic Ind AS blurb (L148) | Meta/repair questions match neither `explain_screen.py` regexes nor any repair handler, so they fall through to `should_fallback_to_ar` (any query with "profit"/"IOCL" qualifies) | `backend/app/brain/explain_screen.py`, `backend/app/knowledge/ar_deep_qa.py` (L40–L48, L169–L174), `turn_runner.py` |
| R3 | **P0 – Blocking** | "Can you take the **VAT** to be 10 instead of 9.25?" (ASR for *WACC*) → "Simulated scenario across 9 records" with a refinery table (L414–L427) | `parse_whatif` only matches `wacc|discount rate|cost of capital`. The planner then classifies the turn as `what_if` and `pipeline.py:370` runs the refinery GRM simulator, even though the latest card is a DCF | `backend/app/finance/dcf/followup.py` (`_WI_FIELDS`, `detect_dcf_followup`), `backend/app/brain/pipeline.py:370` |
| R4 | **P0 – Blocking** | "Show me the total cash flow for the past 10 years" → AR RAG: "disclosures provide … select recent periods rather than a continuous 10-year series" (L257). This is false: the SSOT holds FY17–FY26 | Query lacks the exact phrase `cash flow statement`, so `_EXCLUDE_DIRECT_RE` doesn't block AR. The planner has no "total cash flow" metric, returns nothing, and AR fallback answers. The AR synthesiser is allowed to claim data is missing | `ar_deep_qa.py`, planner metric catalogue / `brain/compiler.py`, `turn_runner.py` |
| R5 | P1 – Important | "He stopped in between." (L196): voice cut off mid-answer after the long AR reply | **(hypothesis — verify in Cloud Run logs)** The AR `spoken_summary` is 4 long sentences with `[AR FY26 p.172]` citations read aloud. It is likely being cut off by the mic-gate watchdog or Live output limits | `ar_deep_qa.py` (spoken builder), `live_session.py` (gate watchdog `GATE_WATCHDOG_S`) |
| R6 | P1 – Important | Overlay chip shows **`IOC.NS $150.50`** (L313) | `OilOverlayBar.tsx:111` uses `$` for every benchmark except `inr` | `frontend/src/components/OilOverlayBar.tsx` |
| R7 | P1 – Important | Spoken numbers use Western grouping and decimals: `₹728,445.4 cr`, `-36461.9 crore` (L32, L83) | Presenter/why templates use `f"{v:,.1f}"` instead of an Indian-lakh formatter | `backend/app/brain/presenter.py`, `fin_diagnostics/why.py` |
| R8 | P1 – Important | DCF permission card: `WACC 9.2534`, `Terminal Growth 3`, `Capex Scale 100` with no units. `Brent 69.04 USD/bbl` sits next to "live BZ=F spot $89.95", which is confusing (L355–L362) | `editable_inputs` values are rendered raw, and the Brent source text mixes the base case with the live spot | `backend/app/agents/dcf_contract.py`, frontend proposal card renderer |
| R9 | P1 – Important | DCF WACC tab is headed **"Statement of Profit and Loss"** and shows `Equity weight (%) 0.63` (L398, L407) | `buildWaccStatement` sets `statement: 'pnl'` (StatementTable label lookup), and weights are fractions labelled `%` | `frontend/src/components/renderers/DcfModelCard.tsx` (L69–L97) |
| R10 | P2 – Cosmetic | User bubble shows `Yeah, please go ahead.You said: Please go ahead`, and the bubble is duplicated (L367, L381) | `confirm.py` echo is sent as a second `user_transcript` and the frontend concatenates it into the same bubble | `live_session.py` (L501, L1030, L1292, L1454), `frontend/src/app/page.tsx` transcript handler |
| R11 | P2 – Cosmetic | DCF result chip says `Source: SSOT` although the price comes from live Yahoo Finance (L387) | Chip derives from first source only | `agents/dcf_agent.py` / `jobs/executor.py` sources + frontend chip |

---

## 1. Step-by-step fixes

### R1 — Profit variance explainer ("Why was FY25 profit so low?")

1. **Period resolution** (`why.py` L28–L31): add `resolve_variance_period(query, session_state)`:
   - "in 24-25 / 2024-25 / FY25 / previous year / last year / 12,962" → `fy_to="FY25"`, `fy_from="FY24"`.
   - If the user contrasts with the current year ("why is it less than 36,802", "compared to this year"), set `compare_to="FY26"` and build **two bridges**: FY24→FY25 (the fall) and FY25→FY26 (the recovery).
   - Match quoted values (e.g. `12,962`, `36,802`) against `PL.PAT` by year in `fact_snapshot.parquet` to pin the year when the user names a number instead of a year.
2. **OMC-grouped bridge** (`variance.py`): collapse the line-level rows into 7 executive buckets with human labels:
   `Net revenue (ex-excise)` · `Crude & product cost (materials + purchases + inventory change)` · `Employee cost` · `Other opex & impairment` · `Depreciation` · `Finance cost` · `Other income & exceptional items` → `PBT`. Then add `Tax` → `PAT`.
   - Add a `LABELS: Dict[str, str]` map so no `PL.*` code ever reaches text or chart.
3. **Operational context**: attach FY24/FY25/FY26 GRM ($12.05 / $4.80 / $10.85), EBITDA margin (from `PL.PBIDT / REV.NET_OF_EXCISE`), and Indian Basket crude (from AR MD&A chunks, e.g. `[AR FY26 p.172]`).
4. **Narrative**: send `{buckets, ops context, top 3 AR chunks}` to Gemini 3 Flash (temp 0.2, `thinking_budget=0`) with the system prompt "answer *why* in 3 sentences, BLUF first, Indian digits, no codes". Then run `check_numeric_grounding`. If the check fails, fall back to a deterministic template that uses the labels plus Indian formatting:
   > "FY25 PAT fell to ₹12,962 crore from ₹39,619 crore mainly because refining and marketing margins collapsed: GRM dropped from $12.05 to $4.80/bbl, so crude & product costs fell far less than revenue (−₹X crore net impact)…"
5. **Visual** (`why.py` L163–L176): emit a renderer-compatible waterfall:
   ```python
   {"type": "chart", "mode": "replace", "title": "Why FY25 PAT fell: PBT bridge FY24 → FY25 (₹ crore)",
    "chart": {"kind": "waterfall", "x": "step", "y": "value_cr", "category": "step", "value": "value_cr",
              "unit": "₹ Cr", "data": [{"step": "FY24 PBT", "value_cr": 52344.21, "type": "total"},
                                       {"step": "Net revenue", "value_cr": ..., "type": "delta"}, …,
                                       {"step": "FY25 PBT", "value_cr": 15882.27, "type": "total"}]},
    "table": {...}, "kpis": [PAT FY24, PAT FY25, GRM FY24→FY25]}
   ```
   Check against the `bridge.to_chart_spec()` format already used in `intents/ui_control.py` (L224–L229) so the frontend renders it.
6. **Repeat guard**: if the new `spoken_summary` equals the previous turn's word for word, regenerate with the user's new wording and the AR narrative instead of repeating the canned text.
7. **Tests**: replay transcript turns L75, L86, L135, L161. Assert the waterfall renders (has `x`, `y`, `type`), the text has no `PL.` codes, FY25 is the "to" year, the text contains `12,962` and `GRM`, and two consecutive answers are not identical.

### R2 — "Which screen are you showing?" / repair turns

1. In `explain_screen.py`, extend `_EXPLAIN_SCREEN_RE` with: `which screen (?:are you|am i) (?:showing|seeing|looking at)`, `what (?:is|are) you showing`, `i(?:'m| am) still seeing`, `(?:screen|chart|this) (?:is not|isn't|doesn't) (?:doing|showing|make)`, `not doing (?:any )?justification`.
2. Add `kind="repair"` with a deterministic reply:
   > "You're right, sir. The screen is still showing the **{active title}** from your earlier question. Let me show the FY24→FY25 profit bridge that explains the drop." Then **re-dispatch** the last unanswered analytical question (stored as `session_state.last_unresolved_query`) through the R1 explainer.
3. In `ar_deep_qa.py`, add a meta-question guard so `should_fallback_to_ar` returns `False` for screen/meta/frustration phrases.
4. Tests: L97, L135, L146 must return `kind in {"explain_screen", "repair"}` and never `provenance.label == "verified_ar"`.

### R3 — WACC misheard as "VAT" / refinery what-if hijack

1. In `followup.py`, add an ASR alias pre-normaliser used only when `find_last_dcf(session_state)["is_latest"]`:
   `\b(vat|wack|whack|wac|vacc|back|what?c)\b` → `wacc`, `\bterminal (?:grow|grove)\b` → `terminal growth`.
2. **Value matching**: if the query has "X instead of Y" or "Y to X" and `Y` equals a current DCF assumption (±0.01, e.g. `9.25 ≈ 9.2534`), map the change to that assumption even without a recognised keyword.
3. In `pipeline.py:370`, if the latest card is `dcf_model` and the query has no refinery/GRM/throughput words, **do not** run the refinery what-if. Return a clarifier instead: "Do you want me to re-run the DCF with WACC at 10%?"
4. Tests: "Can you take the VAT to be 10 instead of 9.25?" after a DCF → `intent=whatif`, `overrides={"wacc_pct": 10.0}`, visual `dcf_model`.

### R4 — "Total cash flow for the past 10 years"

1. Add a cash-flow trend intent (`market/`-style detector or planner metric alias): phrases `total cash flow|cash flow trend|cash flows? (?:for|over) (?:the )?(?:past|last) \d+ years` → multi-series chart `FY17–FY26` of **Operating CF (`CF.CFO`), Investing CF (`CF.CFI`), Financing CF (`CF.CFF`), Free Cash Flow (OCF − Capex), Net change in cash (`CF.NET_CHANGE`)**, read from `fact_snapshot.parquet` / `v_fin_trend_latest`.
2. Add `total\s+cash\s+flow|cash\s+flow\s+(?:trend|for\s+the\s+past)` to `_EXCLUDE_DIRECT_RE` so AR never answers it first.
3. AR guardrail: in the AR synthesiser prompt, forbid statements like "data not available / not a continuous series" for metrics that exist in the SSOT. Drop any such sentence after generation.
4. Tests: L247 query → `visual.type == "chart"`, 10 periods `FY17..FY26`, no `verified_ar` provenance.

### R5 — Voice cut-off on long answers *(verify first)*

1. Pull Cloud Run logs for session 09:44 (`gcloud logging read … "Mic gate watchdog" OR "interrupted"`) to confirm whether the gate watchdog or a barge-in caused the cut.
2. Whatever the cause: add `make_spoken(display_text, max_sentences=2, max_words=45)` that strips `[AR … p.N]` citations, used by AR Deep-QA, why-explainer and explain-screen. Keep the full text in `display_text`.
3. If the watchdog is the cause, raise `GATE_WATCHDOG_S` while `_speak_id` is active.

### R6 — Overlay chip currency
`OilOverlayBar.tsx:111` → use `₹` for `inr` **and** `iocl`, and add the `/sh` suffix for `iocl`.

### R7 — Indian number formatting in speech
Add `fmt_inr_cr(v)` (lakh grouping, no decimals ≥ ₹1,000 crore) in `brain/formatting.py`, and use it in `presenter.py` trend summaries and `why.py`. Test: no `\d{3},\d{3}\.\d` patterns remain in the spoken text of the P&L / cash-flow / why turns.

### R8 — DCF permission card units & Brent clarity
In `dcf_contract.py`, add `display_value` per input (`9.25%`, `3.0%`, `100% of FY26 plan`, `₹150.50/sh`, `$69.04/bbl`). Relabel Brent as `Brent (base case: FY26 avg)` with the source `IOCL AR FY26 · live spot $89.95 — say "use live Brent" to switch`. Add `use live brent` handling in `followup.parse_whatif` (sets `brent_usd` = live `BZ=F`).

### R9 — DCF WACC tab header & weights
In `DcfModelCard.tsx` `buildWaccStatement`, pass a neutral statement kind (or a `label` override) so the header reads **"WACC build-up"**, and multiply `weight_equity` / `weight_debt` by 100 when ≤ 1.

### R10 — Echo bubble duplication
Send the confirm echo as `{"type": "user_transcript", "text": <original utterance>, "is_final": true, "echo": true}`. In `page.tsx`, replace the existing interim bubble instead of appending "You said: …".

### R11 — DCF source chip
When `asm.market_price_inr.source` contains "Yahoo Finance", put the Yahoo source first or set the chip text to `SSOT + Yahoo Finance (live)`.

---

## 2. Verification & release (`v11`)

1. **Golden-conversation regression test**: `tests/test_v11_transcript_replay.py` replays all 19 user turns from `current_refinements.md` in order (Gemini calls mocked for determinism) and asserts the expected route/visual for each turn (P&L statement → FY25 bridge waterfall ×3 → repair → cash-flow statement → 10-yr cash-flow chart → OCF + IOC.NS overlay → stock chart → DCF proposal at live price → confirm → "VAT 10" ⇒ DCF WACC 10%).
2. Run the full backend suite (`PYTHONPATH=. uv run pytest -q`) and the frontend gates (`npm run lint:tokens && npm run lint:contrast && npx tsc --noEmit && npm run build`).
3. Live smoke on Cloud Run: re-ask the four P0 questions by voice.
4. Deploy `yukti-iocl:v11`, update `APP_LINK.md` and `/demo`, then **pause for approval before `git commit` / `git push`**.

## 3. Suggested execution order
R1 → R2 → R3 → R4 (P0, one batch) → R6, R7, R9, R11 (small UI/format fixes) → R8 → R10 → R5 (after log check) → tests → deploy.


---

# `v12` Fix Plan (from `current_refinements.md`, 22-Nov-2026 10:57–11:08 session + Cloud Run logs)

> **Bottom line:** Yahoo Finance data *was* fetched every time (HTTP 200 on IOC.NS / BZ=F / INR=X, latest NSE close ₹150.50 on 20-Nov). Stock-price questions were mis-routed to Annual Report RAG, and the DCF voice was cut because the voice model self-confirmed the DCF and the job announcement was sent twice while Yukti was still speaking.

| # | Severity | Symptom (transcript lines) | Root cause (verified in code / logs) | Fix |
|---|---|---|---|---|
| V1 | **P0** | "show me the current stock price", "historical stock market price of IndianOil for the past 5 years", "plot the stock market price" → AR BSE tables (L338–L537) | `oil_intent._OIL` only matches `(iocl|indianoil) (share|stock)`; Live rewrites to "stock price **of IndianOil**"; `_NOT` blocks any query containing "cash flow / DCF"; Live chose `ui_control overlay=iocl` once (L376–L407) | Word-order-free stock detector (`stock/share/market price`, `stock mrket`, `IOC`), early route before DCF follow-ups, AR exclusion, Live prompt: overlay only when explicitly asked, "latest NSE close" wording on weekends |
| V2 | **P0** | DCF started without the user's "yes"; voice cut mid-sentence (L543–L585) | Live sent "Run the 10-year DCF valuation agent…" → `CONFIRM_RE` matched leading "run"; job finished in ~2 s; announcement `job:…:1` arrived twice (11:07:51.1 / 51.5) while Live was still speaking | Long sentences are not confirmations (affirmative-start or ≤5-word "run it"); dedupe speak ids; defer job announcement until Yukti finishes speaking; Live prompt: never confirm on the user's behalf |
| V3 | P1 | "Why was there a reduction in net profit in FY24-25?" → FY23→FY24 "profit rose" bridge (L215–L245) | `FY24-25` parsed as FY24; "reduction" not a fall word | `FY24-25`/`2024-25` → FY25 only; add reduc*/declin*/lower; reuse previous turn's year |
| V4 | P1 | "Why did net cash reduce in FY24-25?" → 10-year statement, no explanation (L130–L176) | No cash-flow variance skill; trend skill excludes "why" | OCF bridge FY24→FY25 (PBT, non-cash, working capital, tax paid) + waterfall |
| V5 | P1 | Text cut mid-word "(₹1,454 c" (L227, L654) | `display_text` maxLength 600 (schema) truncates long explanations | Keep display ≤ 560 chars; detail in insights |
| V6 | Needs owner action | Google Sheets export → Excel fallback (11:08:21 log: "Service Accounts do not have storage quota") | SA has no My Drive quota | Create a Shared Drive, add `yukti-iocl-sa@yukti-finance-iocl.iam.gserviceaccount.com` as Content Manager, set `YUKTI_GDRIVE_FOLDER_ID` on Cloud Run (code already passes `supportsAllDrives` + `parents`) |
| V7 | P1 | Demo story "internal + external data" not explicit | — | DCF result sentence naming internal SSOT + external Yahoo Finance sources |

Verification: `tests/test_v12_transcript_replay.py` (stock routing, no self-confirm, FY24-25 parsing, cash-flow explainer, display length), full suite, frontend gates, deploy `v12`.

---

# `v13` Fix Plan (from `current_refinements.md`, 22-Nov-2026 11:58–12:04 session + Cloud Run logs)

| # | Severity | Symptom | Root cause | Fix (status) |
|---|---|---|---|---|
| W1 | **P0** | Voice cut at 11:58:39 / 12:03:41 ("Between FY22…") | Cloud Run request timeout 300 s closes WebSockets every 5 min (11:53:37.99 → 11:58:39.26) | `--timeout=3600` (applied) + client renews the socket between turns after 50 min (`refreshIfOld`) |
| W2 | **P0** | "FCF doubled but stock didn't — why?" → stock chart repeated | Stock-chart route matched "stock price" in a why-question | Market-vs-fundamentals skill: FCF bars + IOC.NS FY-average line, premise check, negative years, P/FCF multiple |
| W3 | P1 | "WACC for the past 10 years" → current WACC only | DCF follow-up grabbed "WACC" | FY17–FY26 WACC history from `fact_wacc_annual` |
| W4 | P1 | "Overlay FCF on this" (stock chart) → fake combo | Daily stock vs FY metric | Same combo as W2 (overlay mode) |
| W5 | P1 | "Consolidated cash flow" → standalone shown silently | Only 6 consolidated line codes in SSOT | Explicit "consolidated not in verified data; showing standalone" note |
| W6 | P1 | "Free cash flow for 5 years" narrated OCF | Trend skill not metric-aware | FCF-only chart + narrative |
| W7 | P2 | "Same as FCF?" → generic definition | Conceptual answer ignored data | OCF − capex = FCF with FY26 figures |
| W8 | P2 | DCF WACC tab: "Post-tax Kd 7.15" | 7.15% is pre-tax | Pre-tax 7.15% and post-tax 5.35% rows |
| W9 | P2 | "Salary Component" filter label; weights 0.63 | HR leftover label; fractions | "Component"; weights in % |

---

# `v14` Fixes (22-Nov-2026 14:39–14:51 session + Cloud Run logs)

| # | Severity | Symptom | Root cause | Fix |
|---|---|---|---|---|
| X1 | P1 | "Plot the profit after tax for the past five years" drew every column | Compiled SQL returns helper columns (consolidated PAT/revenue/EBITDA); renderer drew each as a series | Planner FY-trend charts keep only the metric(s) named in the question; multi-metric trends use grouped bars, never waterfall |
| Y1 | **P0** | "WACC to be 10 / set to 10%" ignored; DCF re-ran at 9.25 four times | Live rewrote to "Run the DCF revaluation with the WACC set to 10%": "run … DCF" short-circuited to a new proposal; edit regex missed "set to / to be / from X to"; ranges capped at WACC 5–20% | Parameter+number after a DCF always re-runs the scenario; broad edit phrasing on the permission card and fresh proposals; ranges widened (WACC 3–30%, g −2–8%, Brent $20–200, capex 20–300%) |
| Z1 | **P0** | Excel export 403 as Director (Finance) (14:51:54) | Voice-confirmed DCF jobs had no owner stamp → registered as CMD → ownership check refused DIR_FIN | Confirmation stamps the session principal; executor falls back to the session principal, never CMD |
