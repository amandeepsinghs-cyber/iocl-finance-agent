/**
 * Persona directory for the UI (IOCL Finance & Downstream 8-persona RBAC; D-41 / D-60 / D-66).
 *
 * The SERVER is the source of truth: the picker loads `/api/auth/personas` and the banner reads `/api/auth/me`.
 * This static mirror of `backend/app/brain/app_users.yaml` is only a fallback for labels when the directory has not
 * loaded yet (and for tests).
 */
import type { PersonaType } from '@/contracts/answerContract';

export type PersonaGroup = 'Leadership' | 'Finance';

export interface PersonaInfo {
  id: PersonaType;
  /** short chip label, e.g. "Grade B · Pricing & Excise" */
  short: string;
  display_name: string;
  designation: string;
  group: PersonaGroup;
  tier: 'cmd' | 'director' | 'junior';
  /** how Yukti addresses the user in the greeting */
  address: string;
}

export const PERSONA_DIRECTORY: PersonaInfo[] = [
  // Leadership = IndianOil Chairman & Functional Directors
  { id: 'CMD', short: 'Chairman', display_name: 'Arvinder Singh Sahney', designation: 'Chairman, IndianOil', group: 'Leadership', tier: 'cmd', address: 'Mr. Sahney' },
  { id: 'DIR_FIN', short: 'Director Finance', display_name: 'Anuj Jain', designation: 'Director (Finance) & CFO', group: 'Leadership', tier: 'director', address: 'Mr. Jain' },
  { id: 'DIR_REF', short: 'Director Refineries', display_name: 'Arvind Kumar', designation: 'Director (Refineries)', group: 'Leadership', tier: 'director', address: 'Mr. Kumar' },
  { id: 'DIR_MKT', short: 'Director Marketing', display_name: 'Saumitra P. Srivastava', designation: 'Director (Marketing)', group: 'Leadership', tier: 'director', address: 'Mr. Srivastava' },
  // IOCL Officer Grades A–D (Finance & Downstream analysts; internal keys E1_FIN..E4_FIN)
  { id: 'E1_FIN', short: 'Grade A · Finance', display_name: 'Ajay Deshmukh', designation: 'Accounts Officer (Grade A)', group: 'Finance', tier: 'junior', address: 'Ajay' },
  { id: 'E2_FIN', short: 'Grade B · Pricing & Excise', display_name: 'Praveen Nair', designation: 'Finance Officer — Pricing & Excise (Grade B)', group: 'Finance', tier: 'junior', address: 'Praveen' },
  { id: 'E3_FIN', short: 'Grade C · Treasury & FX', display_name: 'Shailesh E. Kapoor', designation: 'Manager Finance — Crude & Forex (Grade C)', group: 'Finance', tier: 'junior', address: 'Shailesh' },
  { id: 'E4_FIN', short: 'Grade D · Refinery Costing', display_name: 'Santosh Banerjee', designation: 'Sr. Manager Finance — Refinery Costing (Grade D)', group: 'Finance', tier: 'junior', address: 'Santosh' },
];

export const PERSONA_IDS = PERSONA_DIRECTORY.map((p) => p.id);

export function personaInfo(id?: string | null): PersonaInfo | undefined {
  return PERSONA_DIRECTORY.find((p) => p.id === id);
}

export function isJunior(id?: string | null): boolean {
  return personaInfo(id)?.tier === 'junior';
}

/** Rank used for row-action gating (unknown → 0, never defaults to CMD). */
export function personaRank(id?: string | null): number {
  const t = personaInfo(id)?.tier;
  return t === 'cmd' ? 3 : t === 'director' ? 2 : t === 'junior' ? 1 : 0;
}

/** Shape returned by GET /api/auth/personas (P2H.1 backend). */
export interface PublicPersona {
  id: string;
  persona_id: string;
  display_name: string;
  designation: string;
  functional_designation?: string;
  function?: string;
  grade?: string;
  work_centre?: string;
}

/** Question text of a refusal alternative (object or legacy string). */
export function altQuestion(a: { question?: string } | string | null | undefined): string | undefined {
  if (!a) return undefined;
  return typeof a === 'string' ? a : a.question || undefined;
}
