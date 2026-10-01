import { useCallback, useEffect, useState } from 'react'
import { api, type CaseView as Case, getSession } from '../api'
import { AuditList, Button, Card, LayerTag, MoneyTrail, NumberDiff, ProbBars, RecoveryChart, SlaChip, TypeBadge } from '../components'
import { mask, pct, taka, when } from '../lib'
import { SignIn } from './Console'

const DRAFT_NAMES: Record<string, string> = {
  customer_genuine: 'To customer', customer_genuine_no_balance: 'To customer', customer_scam: 'To customer',
  customer_technical: 'To customer', customer_reject_double: 'To customer', customer_reject_false: 'To customer',
  customer_more_info: 'To customer', customer_agent_route: 'To customer', recipient_consent: 'To recipient',
  recipient_neutral: 'To recipient', internal_note: 'Internal note',
}

export default function CaseView({ id, go }: { id: string; go: (to: string) => void }) {
  const [session, setS] = useState(getSession())
  const [c, setCase] = useState<Case | null>(null)
  const [error, setError] = useState('')
  const [revealed, setRevealed] = useState<{ claimant: string; recipient: string | null; intended: string | null } | null>(null)
  const [draftId, setDraftId] = useState<string>('')
  const [lang, setLang] = useState<'en' | 'bn'>('en')
  const [edits, setEdits] = useState<Record<string, { en?: string; bn?: string }>>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [exportRef, setExportRef] = useState('')

  const load = useCallback(() => {
    api.case(id).then((x) => {
      setCase(x)
      setDraftId((d) => d || x.recommendation.drafts[0] || '')
    }).catch((e) => setError(String(e)))
  }, [id])
  useEffect(() => { if (session) load() }, [session, load])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  if (error) return <p className="max-w-7xl mx-auto p-6 text-rose-700">{error}</p>
  if (!c) return <p className="max-w-7xl mx-auto p-6 text-slate-500">Loading case…</p>

  const f = c.facts
  const rec = c.recommendation
  const pred = c.prediction
  const draft = c.drafts[draftId]
  const draftText = draft ? (edits[draftId]?.[lang] ?? (lang === 'bn' ? draft.bn ?? draft.en : draft.en)) : ''
  const needsSupervisor = rec.approval === 'supervisor' && session.role !== 'supervisor'
  const canDecide = ['agent', 'supervisor'].includes(session.role) && ['new', 'human_review'].includes(c.status)

  async function decide(decision: 'approve' | 'edit' | 'override') {
    setBusy(true)
    setError('')
    try {
      setCase(await api.decide(c!.case_id, decision, reason, Object.keys(edits).length ? edits : undefined))
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => go('/console')} className="text-sm text-slate-500 hover:underline">← Queue</button>
        <h1 className="text-xl font-semibold">{c.case_id}</h1>
        {pred && <TypeBadge type={pred.case_type} label={`${pred.label} · ${pct(pred.confidence)}`} />}
        <SlaChip sla={c.sla} />
        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100">{c.status.replace('_', ' ')}</span>
        <div className="ml-auto flex gap-2">
          {!revealed && ['agent', 'supervisor', 'compliance'].includes(session.role) && (
            <Button tone="secondary" onClick={async () => setRevealed(await api.reveal(c.case_id))} title="Every reveal is written to the audit log (R9)">Reveal numbers</Button>
          )}
        </div>
      </div>
      {c.contest && <p className="text-sm bg-amber-50 text-amber-900 rounded-lg p-3">Customer asked for a human-only review: “{c.contest.reason}” ({when(c.contest.at)})</p>}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="space-y-4">
          <Card title="Complaint" tag="facts" right={<span className="text-xs text-slate-500">{c.channel} · {when(c.created_at)}</span>}>
            <p className={`text-sm leading-relaxed ${c.extraction.language === 'bn' ? 'bn' : ''}`}>{c.complaint_text}</p>
            <p className="text-xs text-slate-500 mt-2">Customer {revealed ? revealed.claimant : mask(c.claimant)} · consent {c.consent?.accepted ? 'recorded' : 'missing'}</p>
          </Card>
          <Card title="What the complaint says (M1)" tag="prediction" right={<span className="text-xs text-slate-500">{c.extraction.llm_used ? 'rules + LLM' : 'rules'}</span>}>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Amount</dt><dd>{taka(c.extraction.amount)}</dd>
              <dt className="text-slate-500">Number</dt><dd>{c.extraction.number ? (revealed ? c.extraction.number : mask(c.extraction.number)) : c.extraction.number_last4 ? `…${c.extraction.number_last4}` : '—'}</dd>
              <dt className="text-slate-500">When</dt><dd>{c.extraction.day_offset === null ? '—' : c.extraction.day_offset === 0 ? 'today' : `${c.extraction.day_offset} day(s) ago`}{c.extraction.hour !== null ? `, ~${c.extraction.hour}:00` : ''}</dd>
              <dt className="text-slate-500">TrxID</dt><dd className="font-mono text-xs">{c.extraction.trx_id ?? '—'}</dd>
              <dt className="text-slate-500">Language</dt><dd>{c.extraction.language}</dd>
              <dt className="text-slate-500">Cues</dt><dd className="text-xs">{Object.entries(c.extraction.cues).filter(([, v]) => v).map(([k]) => k).join(', ') || 'none'}</dd>
            </dl>
            {c.extraction.disagreements.length > 0 && <p className="text-xs text-amber-700 mt-2">Rules and LLM disagree on: {c.extraction.disagreements.join(', ')}. Please confirm.</p>}
            <p className="text-xs text-slate-500 mt-2">Matched {c.match.trx_id ?? 'nothing'} · match confidence {pct(c.match.confidence)}</p>
          </Card>
          <Card title="Audit trail" tag="facts" right={<span className="text-xs text-slate-500">hash-chained (R12)</span>}>
            <AuditList entries={c.audit ?? []} />
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Ledger facts" tag="facts">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Transfer</dt><dd>{taka(Number(f.amount))} · {when(String(f.transfer_ts ?? ''))}</dd>
              <dt className="text-slate-500">To</dt><dd>{revealed?.recipient ?? mask(String(f.recipient ?? ''))}</dd>
              <dt className="text-slate-500">Earlier transfers to it</dt><dd>{String(f.earlier_transfers_to_recipient ?? '—')}</dd>
              <dt className="text-slate-500">Moved out since</dt><dd>{taka(Number(f.outflow_since_transfer ?? 0))}</dd>
              <dt className="text-slate-500">Holdable now</dt><dd className="font-semibold">{taka(Number(f.recoverable_now ?? 0))}</dd>
              <dt className="text-slate-500">Others complained</dt><dd>{String(f.other_complainants_on_recipient ?? 0)} customers</dd>
              <dt className="text-slate-500">Sent back already</dt><dd>{f.return_flow ? 'yes' : 'no'}</dd>
              <dt className="text-slate-500">Status</dt><dd>{String(f.status ?? '')}</dd>
            </dl>
          </Card>
          <Card title="Money trail" tag="facts" right={<span className="text-xs text-slate-500">up to the complaint</span>}>
            <MoneyTrail trail={c.trail} revealed={!!revealed} />
          </Card>
          {c.intended.found && c.intended.candidate && (
            <Card title="Intended number (M3)" tag="prediction">
              <NumberDiff intended={revealed?.intended ?? c.intended.candidate} actual={revealed?.recipient ?? String(f.recipient)} positions={c.intended.positions ?? []} revealed={!!revealed} />
              <p className="text-xs text-slate-500 mt-2">Paid {c.intended.count} times before · keypad distance {c.intended.distance}</p>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {pred && (
            <Card title="Case type (M4)" tag="prediction">
              <ProbBars probs={pred.probs} />
              <h4 className="text-xs font-semibold text-slate-500 mt-3 mb-1">Top reasons</h4>
              <ul className="text-sm space-y-1">
                {pred.reasons.map((r) => <li key={r.feature}>• {r.label} <span className="text-slate-500">({String(r.value)})</span></li>)}
              </ul>
            </Card>
          )}
          <Card title="Recoverable over time (M5)" tag="prediction">
            <RecoveryChart curve={c.recoverability.curve} amount={Number(f.amount ?? 0)} />
            <p className="text-xs text-slate-500">Taka at risk if this waits ~24 h: <b>{taka(c.priority.lost_by_waiting)}</b>{c.priority.vulnerable ? ' · vulnerable customer' : ''}</p>
          </Card>
          <Card title="Recommendation" tag="rule" right={<span className="font-mono text-xs">{rec.rule_id}</span>}>
            <p className="text-sm">{rec.summary}</p>
            <div className="flex flex-wrap gap-3 text-xs mt-2 text-slate-600">
              <span>Hold request: <b>{taka(rec.hold_amount)}</b> (capped, R14)</span>
              <span>Needs: <b>{rec.approval}</b></span>
              {rec.aml_flag && <span>AML review: {rec.aml_flag}</span>}
            </div>
            {rec.sop && rec.sop.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-slate-600">Procedure followed: {rec.sop.map((x) => x.id).join(', ')}</summary>
                <ul className="mt-1 space-y-1">
                  {rec.sop.map((x) => <li key={x.id}><b>{x.id} {x.title}.</b> {x.text}</li>)}
                </ul>
                <p className="text-[10px] text-slate-400 mt-1">Mock procedures written for the prototype, not upay's.</p>
              </details>
            )}
            <p className="text-[11px] text-slate-400 mt-1">Ferot never moves money; an authorised upay officer carries out an approved request (MFS Regulations §12.3).</p>
          </Card>
        </div>
      </div>

      <Card title="Drafted replies (M8)" tag="generated" right={
        <div className="flex gap-1 text-xs">
          {(['en', 'bn'] as const).map((l) => <button key={l} onClick={() => setLang(l)} className={`px-2 py-0.5 rounded ${lang === l ? 'bg-slate-800 text-white' : 'bg-slate-100'}`}>{l === 'en' ? 'English' : 'বাংলা'}</button>)}
        </div>}>
        <div className="flex gap-2 flex-wrap mb-3">
          {Object.keys(c.drafts).map((k) => (
            <button key={k} onClick={() => setDraftId(k)} className={`text-xs px-2 py-1 rounded-lg ring-1 ${draftId === k ? 'ring-fuchsia-500 bg-fuchsia-50' : 'ring-slate-200'}`}>
              {DRAFT_NAMES[k] ?? k} <span className="text-slate-400">({k})</span>
            </button>
          ))}
        </div>
        {draft && (
          <>
            <textarea value={draftText} onChange={(e) => setEdits({ ...edits, [draftId]: { ...edits[draftId], [lang]: e.target.value } })}
              rows={4} className={`w-full rounded-lg ring-1 ring-slate-300 p-2 text-sm ${lang === 'bn' ? 'bn' : ''}`} disabled={!canDecide} />
            <div className="flex flex-wrap gap-2 text-[11px] mt-1">
              <LayerTag kind="generated" />
              <span className="text-slate-500">source: {draft.source}</span>
              {draft.audience !== 'internal' && (
                <span className={draft.checks.passed ? 'text-emerald-700' : 'text-rose-700'}>
                  {draft.checks.passed ? '✓ grounded · ✓ no refund promise' : '✗ check failed'}{draft.audience === 'recipient' ? ' · ✓ no tipping off' : ''}
                </span>
              )}
              <span className="text-slate-400">Prototype · not an upay message</span>
            </div>
          </>
        )}
      </Card>

      <Card title="Decision" tag="rule">
        {c.decision ? (
          <p className="text-sm">{c.decision.decision} by <b>{c.decision.actor}</b> ({c.decision.role}) at {when(c.decision.at)}{c.decision.reason ? ` — “${c.decision.reason}”` : ''}. Status: {c.status.replace('_', ' ')}.</p>
        ) : canDecide ? (
          <div className="space-y-2">
            {needsSupervisor && <p className="text-xs text-amber-700">This recommendation needs a supervisor (R6). Sign in as a supervisor to approve, or override with a reason.</p>}
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required to override)" className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 text-sm" />
            <div className="flex gap-2">
              <Button disabled={busy || needsSupervisor} onClick={() => decide(Object.keys(edits).length ? 'edit' : 'approve')}>{Object.keys(edits).length ? 'Approve with edits' : 'Approve recommendation'}</Button>
              <Button tone="danger" disabled={busy || !reason.trim()} onClick={() => decide('override')}>Override</Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Your role ({session.role}) can view but not decide this case.</p>
        )}
        {session.role === 'compliance' && (
          <div className="mt-4 border-t border-slate-100 pt-3 space-y-2">
            <p className="text-xs text-slate-600">Export the evidence pack for a verified request, e.g. a police GD (R13, MFS Regulations §18.2).</p>
            <div className="flex gap-2">
              <input value={exportRef} onChange={(e) => setExportRef(e.target.value)} placeholder="Request reference" className="rounded-lg ring-1 ring-slate-300 px-3 py-1.5 text-sm" />
              <Button tone="secondary" disabled={exportRef.trim().length < 3} onClick={async () => {
                const data = await api.exportCase(c.case_id, exportRef)
                const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
                const a = document.createElement('a'); a.href = url; a.download = `${c.case_id}-evidence.json`; a.click()
                load()
              }}>Export evidence</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
