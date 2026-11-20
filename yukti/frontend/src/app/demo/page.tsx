import type { Metadata } from 'next';
import Link from 'next/link';
import { DemoPlaybookClient } from './DemoPlaybookClient';

export const metadata: Metadata = {
  title: 'Executive Demo Playbook — Yukti IOCL',
  description: '6-Act practice flow for IndianOil (IOCL) Finance & Downstream Intelligence executive demos.',
};

export default function DemoPlaybookPage() {
  return (
    <main className="min-h-screen bg-[var(--canvas)] text-[var(--ink-2)]">
      <div className="max-w-[1080px] mx-auto px-6 py-8">
        <div className="flex items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand/iocl_logo.png"
              alt="IndianOil"
              className="w-12 h-12 rounded-[var(--radius-sm)] object-cover"
            />
            <div>
              <div className="font-display font-bold text-[1.4rem] text-[var(--brand-red)] leading-none">
                Executive Demo Playbook
              </div>
              <div className="text-[0.85rem] text-[var(--ink-3)] mt-1">
                Yukti AI · IndianOil Finance &amp; Downstream · 6-Act Practice Flow (~12 min)
              </div>
            </div>
          </div>
          <Link href="/" className="text-[0.85rem] font-semibold text-[var(--accent-deep)] hover:underline">
            ← Back to Yukti
          </Link>
        </div>

        <p className="text-[0.98rem] text-[var(--ink)] leading-relaxed mb-6">
          Use this standalone practice page to rehearse the full <strong>6-Act IndianOil executive demo</strong> without
          adding any demo clutter to the main app canvas. Open Yukti in a second tab, walk through each prompt by voice
          or text, and check off each step as you practice.
        </p>

        <DemoPlaybookClient />

        <div className="mt-10 pt-4 border-t border-[var(--hairline)] text-[0.78rem] text-[var(--ink-3)]">
          Yukti AI · IndianOil Finance &amp; Downstream Intelligence · Practice Playbook (unlinked from main executive canvas)
        </div>
      </div>
    </main>
  );
}
