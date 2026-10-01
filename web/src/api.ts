// Typed client for the Ferot API. Staff calls carry the signed-in actor and role (prototype only:
// production would take identity from upay's single sign-on, never from the browser).

export type Role = 'agent' | 'supervisor' | 'analyst' | 'compliance'

export interface Sla {
  deadline: string
  working_days_limit: number
  working_days_used: number
  working_days_left: number
  breached: boolean
}

export interface QueueRow {
  case_id: string
  status: string
  created_at: string
  case_type: string | null
  label: string
  confidence: number | null
  amount: number
  recoverable_now: number
  lost_by_waiting: number
  priority: number
  sla: Sla
  channel: string
  language: string | null
  rule_id: string
  approval: string
  recipient_last4: string
}

export interface Reason {
  feature: string
  label: string
  value: number | string
  weight: number
}

export interface TrailStep {
  hop: number
  trx_id: string
  type: string
  from: string
  to: string
  amount: number
  ts: string
  to_kind: string
}

export interface CurvePoint {
  minutes: number
  expected: number
  p_hold: number
}

export interface DraftChecks {
  passed: boolean
  unsupported_numbers?: string[]
  refund_phrases?: string[]
  tipping_phrases?: string[]
}

export interface Draft {
  audience: 'customer' | 'recipient' | 'internal'
  en: string
  bn?: string
  source: string
  checks: { passed: boolean }
  checks_en?: DraftChecks
  checks_bn?: DraftChecks
}

export interface AuditEntry {
  seq: number
  ts: string
  actor: string
  role: string
  action: string
  detail: Record<string, unknown>
  hash: string
}

export interface CaseView {
  case_id: string
  created_at: string
  claimant: string
  channel: string
  complaint_text: string
  status: string
  status_history: { status: string; at: string; by?: string }[]
  consent: Record<string, unknown>
  extraction: {
    amount: number | null
    number: string | null
    number_last4: string | null
    day_offset: number | null
    hour: number | null
    trx_id: string | null
    language: string
    cues: Record<string, boolean>
    sources: Record<string, string>
    disagreements: string[]
    llm_used: boolean
  }
  match: { trx_id: string | null; confidence: number; candidates: { trx_id: string; score: number; amount: number; receiver: string; ts: string }[] }
  facts: Record<string, number | string | boolean>
  trail: TrailStep[]
  intended: { found: boolean; candidate?: string | null; count?: number; distance?: number | null; positions?: number[] }
  prediction: { probs: Record<string, number>; case_type: string; label: string; confidence: number; reasons: Reason[] } | null
  recoverability: { now: number; curve: CurvePoint[] }
  priority: { score: number; lost_by_waiting: number; vulnerable: boolean; sla_risk: number }
  sla: Sla
  recommendation: { rule_id: string; action: string; summary: string; approval: string; hold_amount: number; aml_flag: string | null; drafts: string[]; confidence: number; policy_version: string; sop?: { id: string; title: string; text: string; source: string }[] }
  drafts: Record<string, Draft>
  decision: { decision: string; actor: string; role: string; reason: string; at: string; hold_amount: number } | null
  contest: { reason: string; at: string } | null
  model_version: string
  audit?: AuditEntry[]
}

export interface DemoCustomer {
  key: string
  label: string
  wallet: string
  language: string
  now_minute: number
  now: string
  sample_text: string
  transactions: { trx_id: string; type: string; to: string; amount: number; ts: string }[]
}

export interface CustomerStatus {
  case_id: string
  status: string
  step: number
  steps: string[]
  deadline: string
  helpline: string
  message_en: string
  message_bn: string
  escalation: string
  can_contest: boolean
}

const SESSION_KEY = 'ferot.session'

export interface Session {
  actor: string
  role: Role
}

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function setSession(s: Session | null) {
  try {
    if (s) localStorage.setItem(SESSION_KEY, JSON.stringify(s))
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* storage unavailable: the session lasts for this page only */
  }
}

async function request<T>(path: string, init: RequestInit = {}, staff = false): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const session = getSession()
  if (staff && session) {
    headers['X-Ferot-Actor'] = session.actor
    headers['X-Ferot-Role'] = session.role
  }
  const res = await fetch(`/api/v1${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; model_version: string; llm_provider: string; cases: number }>('/health'),
  demoCustomers: () => request<DemoCustomer[]>('/demo/customers'),
  createComplaint: (body: unknown) =>
    request<{ case_id: string; status: CustomerStatus }>('/complaints', { method: 'POST', body: JSON.stringify(body) }),
  status: (id: string) => request<CustomerStatus>(`/cases/${id}/status`),
  contest: (id: string, reason: string) =>
    request<CustomerStatus>(`/cases/${id}/contest`, { method: 'POST', body: JSON.stringify({ reason }) }),
  queue: () => request<QueueRow[]>('/queue', {}, true),
  case: (id: string) => request<CaseView>(`/cases/${id}`, {}, true),
  decide: (id: string, decision: string, reason: string, edited?: Record<string, { en?: string; bn?: string }>) =>
    request<CaseView>(`/cases/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, reason, edited_drafts: edited ?? null }) }, true),
  reveal: (id: string) =>
    request<{ claimant: string; recipient: string | null; intended: string | null }>(`/cases/${id}/reveal`, { method: 'POST' }, true),
  exportCase: (id: string, request_ref: string) =>
    request<unknown>(`/cases/${id}/export`, { method: 'POST', body: JSON.stringify({ request_ref }) }, true),
  kpis: () => request<Record<string, unknown>>('/insights/kpis', {}, true),
  clusters: () => request<{ wallets: string[]; complainants: number; cash_out_agents: number; first_seen: string }[]>('/insights/clusters', {}, true),
  amlQueue: () => request<{ id: number; case_id: string; wallet: string; role: string; created_at: string }[]>('/insights/aml-queue', {}, true),
  metrics: () => request<Record<string, any>>('/insights/metrics', {}, true),
  simulation: () => request<Record<string, any>>('/insights/simulation', {}, true),
  report: () => request<string>('/insights/dispute-report.csv', {}, true),
  reset: () => request<{ seeded: number }>('/demo/reset', { method: 'POST' }, true),
}
