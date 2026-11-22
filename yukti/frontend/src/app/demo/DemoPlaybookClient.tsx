'use client';

import React, { useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, RotateCcw, Sparkles } from 'lucide-react';

export interface DemoStep {
  id: string;
  stepNumber: number;
  persona: string;
  channel: 'Voice or Text' | 'Voice / Confirm' | 'UI Action + Prompt' | 'Voice (Hindi / Hinglish)';
  prompt: string;
  highlight: string;
  keyNumbers: string[];
}

export interface DemoAct {
  id: string;
  actNumber: number;
  title: string;
  duration: string;
  objective: string;
  steps: DemoStep[];
}

const DEMO_ACTS: DemoAct[] = [
  {
    id: 'act-1',
    actNumber: 1,
    title: 'Statutory Financial Truth: Schedule III P&L & 5-Year Cash Flow',
    duration: '2.5 min',
    objective: 'Establish instant CFO trust: zero LLM arithmetic, 100% verbatim Ind-AS Schedule III figures reconciled to 0.00 Cr.',
    steps: [
      {
        id: 's1',
        stepNumber: 1,
        persona: 'CMD (Arvinder Singh Sahney)',
        channel: 'Voice or Text',
        prompt: "Show IOCL's Schedule III Profit and Loss statement for FY26.",
        highlight: 'Point out the indented Schedule III P&L structure (with Total Income cleanly anchoring the Income section), verbatim FY26 Annual Report p.205 lines, and source citations.',
        keyNumbers: ['Gross Revenue ₹8,86,224 Cr', 'Total Income ₹8,91,213 Cr', 'PAT ₹36,802.42 Cr', 'EPS ₹26.72'],
      },
      {
        id: 's2',
        stepNumber: 2,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'Can I see the Cash Flow statement for the past 5 years?',
        highlight: 'Show sticky Ind-AS 7 Cash Flow rows with FY26 down to FY22 as columns plus the Free Cash Flow KPI tile (+₹44,977 Cr = OCF ₹71,399 Cr less Capex ₹26,421 Cr), setting up the transition to valuation.',
        keyNumbers: ['OCF ₹71,399 Cr (FY26)', 'Capex ₹26,421 Cr', 'Free Cash Flow +₹44,977 Cr'],
      },
    ],
  },
  {
    id: 'act-2',
    actNumber: 2,
    title: 'Live Yahoo Finance Stock Price → Live-Priced DCF Valuation & Formula Export',
    duration: '4.5 min',
    objective: 'Transition from Cash Flow to live NSE:IOC market data via Yahoo Finance API, then run the 10-year DCF directly against that live share price with IB-grade Excel & Google Sheets export.',
    steps: [
      {
        id: 's3',
        stepNumber: 3,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: "Can I see IOCL's stock price movement for the past 5 years?",
        highlight: 'Tell the audience Yukti is connected live to market data through the Yahoo Finance API (IOC.NS, Brent BZ=F, USD/INR). Point out today’s live NSE:IOC share price KPI tile (~₹150.50/sh) and 5-year daily close trajectory.',
        keyNumbers: ['Live Yahoo Finance API (IOC.NS)', 'Today’s live NSE:IOC price', '5-year daily close chart'],
      },
      {
        id: 's4',
        stepNumber: 4,
        persona: 'CMD',
        channel: 'Voice / Confirm',
        prompt: 'Run the DCF valuation model for IOCL on the live market price and tell me if it is undervalued or overvalued.',
        highlight: 'Point out that the human-in-the-loop confirmation card automatically pulls the exact live Yahoo Finance NSE:IOC share price (~₹150.50/sh). Say "Please go ahead." (or click Proceed) and tour the 6 tabs: Summary, FCFF, WACC, Bridge, Sensitivity, and Tornado.',
        keyNumbers: ['Intrinsic ₹265.26/sh', 'Live NSE:IOC ~₹150.50/sh (Yahoo Finance)', 'WACC 9.25%', 'Say "Please go ahead."'],
      },
      {
        id: 's5',
        stepNumber: 5,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'And what are the analysts saying online?',
        highlight: 'Show live Vertex AI Google Search grounding pulling current Street brokerage target prices & ratings for NSE:IOC and comparing them against both our DCF and live market price.',
        keyNumbers: ['Live Google Search Grounding', 'Street targets vs. ₹265.26 DCF'],
      },
      {
        id: 's6',
        stepNumber: 6,
        persona: 'CMD',
        channel: 'UI Action + Prompt',
        prompt: 'Can you change the WACC to 10.25% instead of 9.25% and run the analysis again?',
        highlight: 'Show the full 6-tab recomputation (intrinsic value moves ₹265.26 → ₹218.12/sh). Then click Export → Excel (.xlsx) or Google Sheets to show the 9-sheet IB-formatted workbook with live =SUM / =NPV / =INDEX formulas.',
        keyNumbers: ['₹265.26 → ₹218.12/sh', '9-sheet live-formula .xlsx', '1-click Google Sheets upload'],
      },
      {
        id: 's7',
        stepNumber: 7,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'Can you tell me the growth rate you have assumed from 2027 onwards in revenue, operating profit, and FCF, and does it match historical trend? Give me a plot.',
        highlight: 'Show the side-by-side comparison of assumed FY27–FY36 CAGRs against verified FY17–FY26 historical CAGRs across Revenue, EBIT, and FCFF, then follow up with "And now extend this plot to 2036."',
        keyNumbers: ['FY17–FY26 Actual vs. FY27–FY36 Forecast', 'Revenue 2.00% CAGR', 'Extendable to FY36'],
      },
    ],
  },
  {
    id: 'act-3',
    actNumber: 3,
    title: 'Downstream Operations, Retail Fuel Build-Up & Brent Correlation',
    duration: '2.5 min',
    objective: 'Demonstrate IOCL-specific downstream intelligence across 9 standalone refineries, 10-year retail pump prices, and OMC crude-vs-revenue economics.',
    steps: [
      {
        id: 's8',
        stepNumber: 8,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'Rank all IOCL refineries by GRM ($/bbl) and EBITDA in FY26.',
        highlight: 'Show the 9 standalone refineries (70.25 MMTPA combined capacity) ranked by GRM & EBITDA — Panipat, Paradip, and Koyali leading.',
        keyNumbers: ['9 Standalone Refineries', '70.25 MMTPA', 'Panipat · Paradip · Koyali'],
      },
      {
        id: 's9',
        stepNumber: 9,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'Can you show me the diesel price in Delhi for the past 10 years?',
        highlight: 'Show 10-year PPAC/IOCL retail Diesel (HSD) history in Delhi plus Central Excise + State VAT retail price build-up.',
        keyNumbers: ['₹54.71/L (2016) → ₹87.67/L (2026)', 'Excise + VAT build-up', 'Delhi · Mumbai · Kolkata · Chennai'],
      },
      {
        id: 's10',
        stepNumber: 10,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: "Show IOCL's gross revenue for the past 5 years.",
        highlight: 'Then say "Overlay Brent on this chart" followed by "Why did revenue increase in FY26 even when Brent crude fell?" — Yukti explains IOCL OMC volume growth (+5% to 105.1 MMT), steady pump prices, and why lower crude expanded FY26 PAT +184% while keeping the chart + Brent overlay intact.',
        keyNumbers: ['Brent overlay ($/bbl)', '105.1 MMT volume (+5%)', 'PAT +183.9% to ₹36,802 Cr'],
      },
    ],
  },
  {
    id: 'act-4',
    actNumber: 4,
    title: 'Deep 10-Year Annual Report Intelligence (Vector RAG)',
    duration: '1.5 min',
    objective: 'Prove that Yukti can answer open-ended footnote, capex, and ESG questions across all 10 Annual Reports (3,311 pages).',
    steps: [
      {
        id: 's11',
        stepNumber: 11,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: "What were IOCL's contingent liabilities and green hydrogen plans in the FY26 Annual Report?",
        highlight: 'Point to the grounded [AR FY26 p.NN] citations retrieved live from 8,437 embedded chunks in BigQuery doc_chunks_ar.',
        keyNumbers: ['10 Annual Reports (FY17–FY26)', '8,437 verbatim chunks', 'Inline [AR FY26 p.NN] citations'],
      },
    ],
  },
  {
    id: 'act-5',
    actNumber: 5,
    title: 'Maharatna MoU Governance & Enterprise RBAC Guardrails',
    duration: '1.5 min',
    objective: 'Show board-level MoU tracking and prove deterministic role-based access enforcement.',
    steps: [
      {
        id: 's12',
        stepNumber: 12,
        persona: 'CMD',
        channel: 'Voice or Text',
        prompt: 'How is IOCL tracking against its MoPNG/DPE Maharatna MoU targets?',
        highlight: 'Show IOCL Maharatna MoU KPIs (Capex, PAT/Net Worth, Refinery Throughput, Pipeline Utilization) vs. DPE Excellent targets.',
        keyNumbers: ['MoPNG / DPE Scorecard', 'Actual vs. Excellent Target'],
      },
      {
        id: 's13',
        stepNumber: 13,
        persona: 'Switch to Grade A Officer (E1_FIN)',
        channel: 'UI Action + Prompt',
        prompt: 'Run the DCF valuation model for IOCL.',
        highlight: 'Switch persona in the TopBar to Grade A Officer (E1_FIN) and run the prompt. Highlight the deterministic RBAC refusal with policy citation and safe alternative.',
        keyNumbers: ['Deterministic RBAC refusal', 'Rule reference', 'Zero data leakage'],
      },
    ],
  },
  {
    id: 'act-6',
    actNumber: 6,
    title: 'Bilingual Gemini Live Voice & Architecture Close',
    duration: '1 min',
    objective: 'Close on natural Hindi/Hinglish executive voice interaction and enterprise Google Cloud security.',
    steps: [
      {
        id: 's14',
        stepNumber: 14,
        persona: 'Switch back to CMD',
        channel: 'Voice (Hindi / Hinglish)',
        prompt: 'FY26 mein IndianOil ka net profit aur top 3 refineries kaun si rahi?',
        highlight: 'Speak via the mic orb to demonstrate live bilingual voice, then click the Architecture icon (/architecture) to close on Cloud Run IAP + BigQuery SSOT + Vertex AI.',
        keyNumbers: ['Gemini Live EN/HI/Hinglish', 'Cloud Run IAP', 'BigQuery SSOT + Firestore'],
      },
    ],
  },
];

const STORAGE_KEY = 'yukti_iocl_demo_playbook_done_v1';

export function DemoPlaybookClient() {
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) setDone(JSON.parse(saved));
    } catch {
      // ignore storage errors
    }
  }, []);

  const totalSteps = DEMO_ACTS.reduce((acc, a) => acc + a.steps.length, 0);
  const completedCount = Object.values(done).filter(Boolean).length;

  const toggleStep = (id: string) => {
    setDone((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const resetProgress = () => {
    setDone({});
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  };

  const copyPrompt = async (id: string, prompt: string) => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedId(id);
      setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1800);
    } catch {
      // fallback ignored
    }
  };

  return (
    <div className="space-y-6">
      {/* Progress & quick-launch bar */}
      <div className="rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--card)] p-5 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[var(--ink)] font-semibold">
            <Sparkles className="w-4 h-4 text-[var(--brand-red)]" />
            <span>Rehearsal Progress: {completedCount} / {totalSteps} steps practiced</span>
          </div>
          <div className="w-64 h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
            <div
              className="h-full bg-[var(--accent)] transition-all duration-300"
              style={{ width: `${Math.round((completedCount / Math.max(totalSteps, 1)) * 100)}%` }}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={resetProgress}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-sm)] border border-[var(--hairline)] bg-[var(--surface)] text-[0.84rem] font-medium text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset checklist
          </button>
          <a
            href="/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--accent-deep)] text-[var(--on-accent)] text-[0.85rem] font-semibold hover:opacity-95 transition-opacity"
          >
            Open Yukti App (New Tab)
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* Acts */}
      {DEMO_ACTS.map((act) => (
        <section
          key={act.id}
          className="rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--card)] overflow-hidden"
        >
          <div className="px-5 py-4 bg-[var(--surface)] border-b border-[var(--hairline)] flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[0.75rem] font-semibold uppercase tracking-wider text-[var(--brand-red)]">
                Act {act.actNumber} · {act.duration}
              </div>
              <h2 className="font-display text-[1.12rem] font-bold text-[var(--ink)] mt-0.5">
                {act.title}
              </h2>
              <p className="text-[0.86rem] text-[var(--ink-2)] mt-1">{act.objective}</p>
            </div>
          </div>

          <div className="divide-y divide-[var(--hairline)]">
            {act.steps.map((step) => {
              const isDone = !!done[step.id];
              const isCopied = copiedId === step.id;
              return (
                <div
                  key={step.id}
                  className={`p-5 transition-colors ${isDone ? 'bg-[var(--surface)]/60' : 'bg-[var(--card)]'}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3.5 min-w-0 flex-1">
                      <button
                        type="button"
                        onClick={() => toggleStep(step.id)}
                        aria-label={`Mark step ${step.stepNumber} practiced`}
                        className={`mt-0.5 shrink-0 w-6 h-6 rounded-full border grid place-items-center transition-colors ${
                          isDone
                            ? 'bg-[var(--positive)] border-[var(--positive)] text-[var(--on-accent)]'
                            : 'border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-3)] hover:border-[var(--accent)]'
                        }`}
                      >
                        {isDone ? <Check className="w-3.5 h-3.5" /> : <span className="text-[0.72rem] font-semibold">{step.stepNumber}</span>}
                      </button>

                      <div className="min-w-0 flex-1 space-y-2.5">
                        <div className="flex flex-wrap items-center gap-2 text-[0.76rem]">
                          <span className="px-2 py-0.5 rounded-full bg-[var(--accent-pale)] text-[var(--accent-deep)] font-semibold">
                            {step.persona}
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-[var(--surface-2)] text-[var(--ink-2)] font-medium">
                            {step.channel}
                          </span>
                        </div>

                        <blockquote className="text-[0.98rem] font-medium text-[var(--ink)] leading-snug border-l-2 border-[var(--brand-red)] pl-3">
                          “{step.prompt}”
                        </blockquote>

                        <p className="text-[0.86rem] text-[var(--ink-2)] leading-relaxed">
                          <strong className="text-[var(--ink)]">Highlight on screen:</strong> {step.highlight}
                        </p>

                        <div className="flex flex-wrap gap-1.5 pt-0.5">
                          {step.keyNumbers.map((num) => (
                            <span
                              key={num}
                              className="text-[0.75rem] px-2.5 py-0.5 rounded-[var(--radius-sm)] border border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-2)] font-mono"
                            >
                              {num}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => copyPrompt(step.id, step.prompt)}
                      className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--hairline)] bg-[var(--surface)] text-[0.8rem] font-medium text-[var(--ink-2)] hover:text-[var(--ink)] hover:border-[var(--accent)] transition-colors"
                    >
                      {isCopied ? <Check className="w-3.5 h-3.5 text-[var(--positive)]" /> : <Copy className="w-3.5 h-3.5" />}
                      {isCopied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
