// Plain names for codes the API returns.

export const STATUS: Record<string, string> = {
  new: 'New',
  human_review: 'Human review',
  manual_review: 'Manual review',
  hold_requested: 'Hold requested',
  consent_requested: 'Consent requested',
  with_tech_ops: 'With tech operations',
  rejected: 'Rejected',
  with_distributor: 'With distributor',
  awaiting_customer: 'Waiting for customer',
  in_progress: 'In progress',
}

export const OPEN = ['new', 'human_review']

export const CHANNEL: Record<string, string> = { app: 'App', call: 'Phone call', sms: 'SMS', email: 'Email' }

export const LANGUAGE: Record<string, string> = { bn: 'Bangla', en: 'English', banglish: 'Banglish' }

export const APPROVER: Record<string, string> = { agent: 'an agent', supervisor: 'a supervisor', compliance: 'compliance' }

export const status = (s: string) => STATUS[s] ?? s.replace(/_/g, ' ')
