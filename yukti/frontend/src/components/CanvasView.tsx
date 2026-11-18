'use client';

import { altQuestion } from '@/personas';
import { PERSONA_DIRECTORY } from '@/personas';
import React, { useEffect, useState } from 'react';
import { VoiceOrb, OrbState } from './VoiceOrb';
import { VoiceAudioEngine } from '@/services/audioAnalyser';
import { ChatMessage } from './FloatingConversationPanel';
import { ConversationFeed } from './ConversationFeed';
import { AnswerCard } from './AnswerCard';
import type { Turn } from '@/state/feed';
import type { SpecPatch, VisualContainer } from '@/contracts/answerContract';
import { latestAnswered } from '@/state/feed';
import { Users, TrendingUp, Target, Scale, BarChart3, Activity } from 'lucide-react';
import { Card } from './ui/primitives';

interface CanvasViewProps {
  /** conversation feed (U2.2); empty = greeting */
  turns: Turn[];
  isDark?: boolean;
  onNavigateToAlternative?: (q?: string) => void;
  onSelectStarter?: (q: string) => void;
  onAsk?: (q: string, specPatch?: SpecPatch) => void;
  onRetry?: (q: string, turnId?: string) => void;
  onNewSession?: () => void;
  onReplot?: (turnId: string, visual: VisualContainer) => void;
  busy?: boolean;
  statusLine?: string | null;
  onTalk?: () => void;
  isMicActive?: boolean;
  orbState?: OrbState;
  audioEngine?: VoiceAudioEngine;
  messages?: ChatMessage[];
  liveInterimText?: string;
  /** active persona: drives the greeting name and suggestion cards (U4.5) */
  persona?: string;
}

/** Feed is on unless explicitly disabled (NEXT_PUBLIC_FEED_V2=0 falls back to the single-answer canvas). */
const FEED_V2 = process.env.NEXT_PUBLIC_FEED_V2 !== '0';

type Starter = { icon: React.ComponentType<{ className?: string }>; tag: string; title: string; q: string };

// U4.5: IOCL Finance & Downstream persona starters. Grades A–D get public statement / aggregate / WACC / DCF asks.
const STARTERS: Record<string, Starter[]> = {
  CMD: [
    { icon: TrendingUp, tag: 'Finance · 10-Yr P&L', title: '10-year Gross vs Net Revenue & PAT', q: 'Show 10-year Gross vs Net-of-Excise revenue, EBITDA, and PAT from FY17 to FY26' },
    { icon: Activity, tag: 'Refineries · GRM', title: 'Refinery GRM & fuel-loss 360', q: 'Compare FY26 throughput, capacity utilisation, and GRM across all 9 IndianOil refineries' },
    { icon: BarChart3, tag: 'Valuation · NSE:IOC', title: 'Live NSE:IOC DCF valuation', q: 'Run a discounted cash flow valuation for IndianOil (NSE:IOC) using FY26 WACC' },
    { icon: Target, tag: 'Performance · MoU', title: 'MoU scorecard FY26', q: 'How is IndianOil tracking against MoPNG MoU scorecard targets in FY26?' },
  ],
  DIR_FIN: [
    { icon: TrendingUp, tag: 'Finance · Variance', title: 'FY24→FY25→FY26 PAT bridge', q: 'Explain the PAT bridge across FY24, FY25, and FY26 with GRM and Brent/FX drivers' },
    { icon: BarChart3, tag: 'Valuation · NSE:IOC', title: 'Live NSE:IOC DCF & WACC', q: 'Run a discounted cash flow valuation for IndianOil and show FY17–FY26 WACC build-up' },
    { icon: Scale, tag: 'Capital · Sub-ledgers', title: 'Counterparty credit & working capital', q: 'Show working capital, inventory days, and top CFO value-creation levers for FY26' },
    { icon: Target, tag: 'Governance · DoA', title: 'Delegation of Authority & Board pack', q: 'Summarise IndianOil Finance & DoA governance rules and draft Board CFO highlights' },
  ],
  DIR_REF: [
    { icon: Activity, tag: 'Refineries · 360', title: '9 refineries throughput & GRM', q: 'Compare FY26 throughput, utilisation %, fuel & loss %, and GRM across all 9 refineries' },
    { icon: TrendingUp, tag: 'Macro · GRM Bridge', title: 'Brent, GRM & INR sensitivity', q: 'What is the impact on IndianOil EBITDA and PAT if GRM drops by $2/bbl or INR depreciates?' },
    { icon: BarChart3, tag: 'Refineries · Capex', title: 'Panipat, Paradip & Gujarat expansion', q: 'Show refining segment EBITDA and capex deployment for FY26' },
    { icon: Target, tag: 'Performance · MoU', title: 'Refinery energy & distillate yield', q: 'How is IndianOil tracking on distillate yield and energy intensity MoU targets?' },
  ],
  DIR_MKT: [
    { icon: BarChart3, tag: 'Marketing · Volumes', title: 'MS, HSD, ATF & Indane LPG mix', q: 'Show FY26 marketing product mix across MS, HSD, ATF, and Indane LPG' },
    { icon: TrendingUp, tag: 'Pipelines · Throughput', title: 'Cross-country pipeline throughput', q: 'Summarise FY26 cross-country pipeline throughput and operating margin' },
    { icon: Activity, tag: 'Margins · OMC', title: 'Excise duty & marketing margin impact', q: 'Compare Gross vs Net-of-Excise revenue and marketing under-recovery dynamics in FY25–FY26' },
    { icon: Target, tag: 'Performance · MoU', title: 'Retail network & LPG targets', q: 'How is Marketing division tracking against FY26 MoU milestones?' },
  ],
  E2_FIN: [
    { icon: TrendingUp, tag: 'Finance · Public', title: '10-year Schedule III Revenue & PAT', q: 'Show 10-year Gross vs Net-of-Excise revenue and PAT from FY17 to FY26' },
    { icon: Activity, tag: 'Refineries · Aggregate', title: 'Refinery GRM & throughput 360', q: 'Compare FY26 throughput and GRM across all 9 IndianOil refineries' },
    { icon: BarChart3, tag: 'Valuation · NSE:IOC', title: 'Live NSE:IOC DCF & WACC', q: 'Run a discounted cash flow valuation for IndianOil (NSE:IOC)' },
    { icon: Scale, tag: 'Policy · Public', title: 'Finance & DoA policy summary', q: 'What are the key Finance and Delegation of Authority guidelines?' },
  ],
};
// IOCL Officer Grades A–D (E1_FIN..E4_FIN) share the public statutory / aggregate / WACC / DCF starters
for (const id of ['E1_FIN', 'E3_FIN', 'E4_FIN']) STARTERS[id] = STARTERS.E2_FIN;

const ADDRESS: Record<string, string> = Object.fromEntries(PERSONA_DIRECTORY.map((p) => [p.id, p.address]));

function greetingWord(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

const Greeting: React.FC<{
  onSelect?: (q: string) => void;
  onTalk?: () => void;
  isMicActive?: boolean;
  orbState?: OrbState;
  isDark?: boolean;
  audioEngine?: VoiceAudioEngine;
  messages?: ChatMessage[];
  liveInterimText?: string;
  persona?: string;
}> = ({ onSelect, onTalk, isMicActive, orbState = 'idle', isDark = false, audioEngine, messages = [], liveInterimText, persona }) => {
  const lastTurn = messages[messages.length - 1];
  // P2H.2 G4 M3: unknown / not-signed-in persona gets no starter questions (never the CMD set)
  const starters = (persona && STARTERS[persona]) || [];
  // Time-aware greeting computed on the client after mount (server render may run in UTC).
  const [hello, setHello] = useState('Hello');
  useEffect(() => setHello(greetingWord()), []);
  // Orb scales with the fluid type scale (rem), so it keeps its proportion on 4K / big screens.
  const [orbPx, setOrbPx] = useState(236);
  useEffect(() => {
    const fit = () => {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      // aurora wave on the greeting (≈ 236 px at 1440p, scales on 4K); sponsor preferred this over the 288 px trial (26-Oct)
      setOrbPx(Math.round(Math.min(420, Math.max(200, rem * 14.75))));
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  const name = (persona && ADDRESS[persona]) || ''; // M3: no CMD name for an unknown persona

  return (
    <div className="relative flex-1 flex flex-col items-center justify-between text-center px-6 pt-4 pb-32 w-full min-h-[calc(100vh-14.5rem)]" data-testid="greeting">
      {/* AI aura bloom (D-16): feathery pastel light behind Yukti's presence only (static per D-25) */}
      <div className="pointer-events-none absolute -inset-x-16 -top-10 h-[80%] [mask-image:radial-gradient(ellipse_at_center,black_35%,transparent_72%)] [-webkit-mask-image:radial-gradient(ellipse_at_center,black_35%,transparent_72%)]" aria-hidden>
        <div className="yk-aura-bloom" />
      </div>

      <div className="relative my-auto flex flex-col items-center max-w-[60rem] w-full">
        {/* FEAT-004 / V12 / D-29: centre-stage "Aurora wave" voice orb above the greeting (the sponsor-selected design,
            restored 26-Oct after the 23-Oct WIP snapshot swapped it for a cloud sphere; refs in docs/design_refs/aurora_wave).
            Tap to talk; it reflects listening / thinking / speaking via orbState + the live audio engine. */}
        <div className="relative flex flex-col items-center" data-testid="greeting-talk">
          <VoiceOrb
            state={orbState}
            isDark={isDark}
            size={orbPx}
            onClick={onTalk}
            audioEngine={audioEngine}
            label={orbState === 'speaking' ? 'Stop Yukti speaking' : isMicActive ? 'Stop listening' : 'Start talking to Yukti'}
            pressed={!!isMicActive}
          />
        </div>

        <h1 className="mt-6 text-display font-display text-[var(--ink)]">
          {name ? `${hello}, ${name}` : hello}
        </h1>
        <p className="mt-2 text-body text-[var(--ink-2)]">I&apos;m Yukti, IndianOil&apos;s Finance &amp; Downstream intelligence partner. Ask by voice or type below.</p>

        {liveInterimText ? (
          <p className="mt-5 text-body text-[var(--ink-2)] max-w-[44rem] animate-pulse">&ldquo;{liveInterimText}&rdquo;</p>
        ) : lastTurn ? (
          <p className="mt-5 text-body text-[var(--ink-2)] max-w-[42rem]">{lastTurn.text}</p>
        ) : null}
      </div>

      <div className="relative mt-auto pt-8 w-full max-w-[54rem] flex flex-col items-center gap-1.5" data-testid="starter-cards">
        {starters.slice(0, 3).map((c) => (
          <button
            key={c.title}
            type="button"
            onClick={() => onSelect?.(c.q)}
            className="text-center px-3 py-1 text-caption font-normal text-[var(--ink-3)] hover:text-[var(--ink-2)] transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
          >
            {c.q}
          </button>
        ))}
      </div>
    </div>
  );
};

export const CanvasView: React.FC<CanvasViewProps> = ({
  turns,
  isDark = false,
  onNavigateToAlternative,
  onSelectStarter,
  onAsk,
  onRetry,
  onNewSession,
  onReplot,
  busy,
  statusLine,
  onTalk,
  isMicActive,
  orbState = 'idle',
  audioEngine,
  messages = [],
  persona,
  liveInterimText,
}) => {
  const latest = latestAnswered(turns);
  return (
    <div className={`min-h-full flex flex-col px-[2.25rem] pt-[1.25rem] ${turns.length ? 'pb-[2.5rem]' : 'pb-[9.5rem]'} gap-[1.15rem] max-w-[104rem] mx-auto w-full`} data-testid="canvas">
      {busy && <div className="fixed left-0 right-0 top-[var(--topbar-h)] h-[2px] yk-shimmer z-20" aria-hidden />}

      {turns.length === 0 ? (
        <Greeting
          onSelect={onSelectStarter}
          onTalk={onTalk}
          isMicActive={isMicActive}
          orbState={orbState}
          isDark={isDark}
          audioEngine={audioEngine}
          messages={messages}
          liveInterimText={liveInterimText}
          persona={persona}
        />
      ) : FEED_V2 ? (
        <ConversationFeed
          turns={turns}
          isDark={isDark}
          persona={persona}
          statusLine={statusLine}
          liveInterimText={liveInterimText}
          onAsk={onAsk}
          onRetry={onRetry}
          onNewSession={onNewSession}
          onReplot={onReplot}
          onNavigateToAlternative={onNavigateToAlternative}
        />
      ) : latest?.contract ? (
        <AnswerCard
          key={latest.id}
          contract={latest.contract}
          question={latest.question}
          isDark={isDark}
          persona={persona}
          fresh={latest.fresh}
          isLatest
          onAsk={onAsk}
          onReplot={onReplot ? (v) => onReplot(latest.id, v) : undefined}
          onNavigateToAlternative={() => onNavigateToAlternative?.(altQuestion(latest.contract?.access?.alternative))}
        />
      ) : null}
    </div>
  );
};
