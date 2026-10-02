import { useCallback, useEffect, useState } from 'react'
import { api, type CaseView as Case, getSession, type Network } from '../api'
import { AuditList, Button, ContribBars, NumberDiff, Notice, Panel, ProbBars, RingGraph, SlaText, TakaDrain, TypeMark } from '../components'
import { day, mask, pct, taka, TYPE_TONE, when } from '../lib'
import { APPROVER, CHANNEL, LANGUAGE, OPEN, status } from '../lib-labels'
import { SignIn, UserChip } from './Console'

const DRAFT_NAMES: Record<string, string> = {
  customer_genuine: 'To the customer', customer_genuine_no_balance: 'To the customer', customer_scam: 'To the customer',
  customer_technical: 'To the customer', customer_reject_double: 'To the customer', customer_reject_false: 'To the customer',
  customer_more_info: 'To the customer', customer_agent_route: 'To the customer', recipient_consent: 'To the recipient',
  recipient_neutral: 'To the recipient', internal_note: 'Internal note',
}

function Check({ ok, children }: { ok: boolean; children: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${ok ? 'text-flag' : 'text-signal-2'}`}>
      <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
        {ok ? <path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
          : <path d="M7 7l10 10M17 7 7 17" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />}
      </svg>
      {children}
    </span>
  )
}

export default function CaseView({ id, go }: { id: string; go: (to: string) => void }) {
  const [session, setS] = useState(getSession())
  const [c, setCase] = useState<Case | null>(null)
  const [net, setNet] = useState<Network | null>(null)
  const [error, setError] = useState('')
  const [revealed, setRevealed] = useState<{ claimant: string; recipient: string | null; intended: string | null } | null>(null)
  const [draftId, setDraftId] = useState('')
  const [lang, setLang] = useState<'en' | 'bn'>('en')
  const [edits, setEdits] = useState<Record<string, { en?: string; bn?: string }>>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [exportRef, setExportRef] = useState('')

  const load = useCallback(() => {
    api.case(id).then((x) => {
      setCase(x)
      setDraftId((d) => d || x.recommendation.drafts[0] || Object.keys(x.drafts)[0] || '')
    }).catch((e) => setError(String(e.message ?? e)))
    api.network(id).then(setNet).catch(() => setNet(null))
  }, [id])
  useEffect(() => { if (session) load() }, [session, load])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  if (!c) {
    return (
      <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-10">
        {error ? <Notice tone="signal">{error}</Notice> : <p className="text-ink-3">Opening the case file…</p>}
      </div>
    )
  }

  const f = c.facts
  const rec = c.recommendation
  const pred = c.prediction
  const draft = c.drafts[draftId]
  const draftText = draft ? (edits[draftId]?.[lang] ?? (lang === 'bn' ? draft.bn ?? draft.en : draft.en)) : ''
  const needsSupervisor = rec.approval === 'supervisor' && session.role !== 'supervisor'
  const canDecide = ['agent', 'supervisor'].includes(session.role) && OPEN.includes(c.status)
  const tone = (pred && TYPE_TONE[pred.case_type]) || '#6b7f78'
  const recipient = revealed?.recipient ?? mask(String(f.recipient ?? ''))

  async function decide(decision: 'approve' | 'edit' | 'override') {
    setBusy(true)
    setError('')
    try {
      await api.decide(c!.case_id, decision, reason, Object.keys(edits).length ? edits : undefined)
      load()
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-8">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => go('/console')} className="inline-flex items-center gap-1.5 text-[14px] text-ink-2 hover:text-ink">
          <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5 8 12l7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          Queue
        </button>
        <div className="ml-auto"><UserChip onOut={() => setS(null)} /></div>
      </div>

      <header className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <h1 className="num text-[34px] font-semibold leading-none">{c.case_id}</h1>
          <p className="mt-2 text-[14px] text-ink-2">
            Opened {when(c.created_at)} by {CHANNEL[c.channel]?.toLowerCase() ?? c.channel}, customer {revealed?.claimant ?? mask(c.claimant)}
          </p>
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-2 text-[14.5px]">
          <div><dt className="text-[12.5px] text-ink-3">Case type</dt><dd>{pred ? <TypeMark type={pred.case_type} label={pred.label} confidence={pred.confidence} /> : 'Needs information'}</dd></div>
          <div><dt className="text-[12.5px] text-ink-3">Status</dt><dd className="font-medium">{status(c.status)}</dd></div>
          <div><dt className="text-[12.5px] text-ink-3">Deadline, {day(c.sla.deadline)}</dt><dd><SlaText sla={c.sla} /></dd></div>
        </dl>
        <div className="md:ml-auto">
          {!revealed && ['agent', 'supervisor', 'compliance'].includes(session.role) && (
            <Button tone="secondary" size="sm" onClick={async () => setRevealed(await api.reveal(c.case_id))} title="Every reveal is written to the audit log">Reveal numbers</Button>
          )}
          {revealed && <span className="text-[13px] text-ink-3">Numbers revealed. This was logged.</span>}
        </div>
      </header>

      {c.contest && (
        <div className="mt-4"><Notice>The customer asked for a human review on {when(c.contest.at)}: “{c.contest.reason}”</Notice></div>
      )}

      <div className="mt-6">
        {c.recoverability.curve.length && f.transfer_ts ? (
          <TakaDrain amount={Number(f.amount)} past={c.recoverability.past ?? []} curve={c.recoverability.curve} trail={c.trail}
            transferTs={String(f.transfer_ts)} complaintTs={String(f.complaint_ts ?? c.created_at)}
            lostByWaiting={c.priority.lost_by_waiting} waitHours={2} />
        ) : (
          <Notice tone="turmeric">No transfer matched this complaint yet, so there is no money trail. Ask the customer for the TrxID or the time of the transfer.</Notice>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] gap-6 items-start">
        <div className="space-y-6 min-w-0">
          {c.report && (
            <Panel title="Case report" kind="generated" aside={<span className="text-[12.5px] text-ink-3">Written by code from this case file</span>}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                <div className="space-y-5">
                <section>
                  <h4 className="text-[14px] font-semibold text-ink-2">What happened</h4>
                  <p className="mt-1 text-[15px]">{c.report.what_happened}</p>
                </section>
                <section>
                  <h4 className="text-[14px] font-semibold text-ink-2">What the evidence says</h4>
                  <ul className="mt-1 space-y-1 text-[15px]">
                    {c.report.why_risky.map((w) => <li key={w} className="flex gap-2.5"><span className="mt-[9px] w-1.5 h-1.5 rounded-full shrink-0" style={{ background: tone }} aria-hidden="true" />{w}</li>)}
                  </ul>
                </section>
                </div>
                <div className="space-y-5">
                <section>
                  <h4 className="text-[14px] font-semibold text-ink-2">Next step</h4>
                  <p className="mt-1 text-[15px]">{c.report.next_step}</p>
                </section>
                <section>
                  <h4 className="text-[14px] font-semibold text-ink-2">Limits</h4>
                  <ul className="mt-1 space-y-1 text-[14.5px] text-ink-2">
                    {c.report.limits.map((w) => <li key={w} className="flex gap-2.5"><span className="mt-[9px] w-1.5 h-1.5 rounded-full shrink-0 bg-ink-3" aria-hidden="true" />{w}</li>)}
                  </ul>
                </section>
                </div>
              </div>
            </Panel>
          )}

          {pred && (
            <Panel title="Why the model thinks so" kind="prediction">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-6">
                <div>
                  <h4 className="text-[14px] font-semibold text-ink-2 mb-2">Probability of each case type</h4>
                  <ProbBars probs={pred.probs} />
                </div>
                <div>
                  <h4 className="text-[14px] font-semibold text-ink-2 mb-2">Facts that pushed it to “{pred.label.toLowerCase()}”</h4>
                  <ContribBars reasons={pred.reasons} tone={tone} />
                </div>
              </div>
              <p className="mt-4 text-[12.5px] text-ink-3">Case classifier (M4, LightGBM). Bar length is each fact's TreeSHAP contribution in log-odds.</p>
            </Panel>
          )}

          {net && net.center && (
            <Panel title="Around the receiving wallet" kind="facts">
              <p className="text-[14.5px] text-ink-2">
                {net.complainants > 0
                  ? `${net.complainants} other ${net.complainants === 1 ? 'customer' : 'customers'} sent money to ${recipient} and complained. `
                  : `No one else has complained about ${recipient}. `}
                In the 30 days before this complaint it passed money on to {net.nodes.filter((n) => !['center', 'complainant', 'this_customer'].includes(n.kind)).length} accounts.
              </p>
              <div className="mt-3 -mx-2"><RingGraph network={net} revealed={!!revealed} /></div>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-3">
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-turmeric" />This customer</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-signal-soft border border-signal" />Other complainants</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-signal" />Cash-out agents</span>
                <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-surface border border-ink-2" />Other wallets</span>
                <span>Line width shows the amount.</span>
              </div>
            </Panel>
          )}

          <Panel title="The complaint" kind="facts" aside={<span className="text-[12.5px] text-ink-3">{CHANNEL[c.channel] ?? c.channel}, {LANGUAGE[c.extraction.language] ?? c.extraction.language}</span>}>
            <blockquote className="text-[17px] leading-relaxed border-l-2 border-line pl-4">{c.complaint_text}</blockquote>
            <h4 className="mt-5 text-[14px] font-semibold text-ink-2">What Ferot read from it <span className="font-normal text-ink-3">({c.extraction.llm_used ? 'rules and the language model' : 'rules only'})</span></h4>
            <dl className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-[14.5px]">
              <div><dt className="text-[12.5px] text-ink-3">Amount</dt><dd className="num">{taka(c.extraction.amount)}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Number</dt><dd className="num">{c.extraction.number ? (revealed ? c.extraction.number : mask(c.extraction.number)) : c.extraction.number_last4 ? `ends ${c.extraction.number_last4}` : '—'}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">When</dt><dd>{c.extraction.day_offset === null ? '—' : c.extraction.day_offset === 0 ? 'Today' : `${c.extraction.day_offset} days ago`}{c.extraction.hour !== null ? `, about ${String(c.extraction.hour).padStart(2, '0')}:00` : ''}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Matched transfer</dt><dd className="num">{c.match.trx_id ?? 'None'} <span className="text-ink-3">{c.match.trx_id ? pct(c.match.confidence) : ''}</span></dd></div>
            </dl>
            {Object.values(c.extraction.cues).some(Boolean) && (
              <p className="mt-3 text-[13.5px] text-ink-2">Mentions: {Object.entries(c.extraction.cues).filter(([, v]) => v).map(([k]) => k.replace('_', ' or ')).join(', ')}</p>
            )}
            {c.extraction.disagreements.length > 0 && <div className="mt-3"><Notice>Rules and the language model disagree on {c.extraction.disagreements.join(', ')}. Please confirm with the customer.</Notice></div>}
          </Panel>
        </div>

        <div className="space-y-6 min-w-0 lg:sticky lg:top-4">
          <Panel title="Recommendation" kind="rule" aside={<span className="num text-[13px] text-ink-2">{rec.rule_id}</span>}>
            <p className="text-[16px] leading-snug">{rec.summary}</p>
            <dl className="mt-4 grid grid-cols-2 gap-4">
              <div><dt className="text-[12.5px] text-ink-3">Hold request</dt><dd className="num text-[24px] font-semibold text-flag">{taka(rec.hold_amount)}</dd><dd className="text-[12.5px] text-ink-3">Capped at what is left of the disputed amount</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Needs approval from</dt><dd className="text-[16px] font-medium mt-1">{APPROVER[rec.approval] ? APPROVER[rec.approval][0].toUpperCase() + APPROVER[rec.approval].slice(1) : rec.approval}</dd>{rec.aml_flag && <dd className="text-[12.5px] text-signal-2 mt-1">Receiving wallet goes to AML review</dd>}</div>
            </dl>
            {rec.sop && rec.sop.length > 0 && (
              <details className="mt-4 text-[14px] group">
                <summary className="cursor-pointer text-ink-2 hover:text-ink">Procedure followed: {rec.sop.map((x) => x.id).join(', ')}</summary>
                <ul className="mt-2 space-y-2">
                  {rec.sop.map((x) => <li key={x.id}><b>{x.id}, {x.title}.</b> {x.text}</li>)}
                </ul>
                <p className="mt-2 text-[12.5px] text-ink-3">Mock procedures written for the prototype, not upay's.</p>
              </details>
            )}

            <div className="mt-5 pt-4 border-t border-line">
              {c.decision ? (
                <p className="text-[14.5px]">
                  <b>{{ approve: 'Approved', edit: 'Approved with edits', override: 'Overridden' }[c.decision.decision] ?? c.decision.decision}</b> by {c.decision.actor} ({c.decision.role}), {when(c.decision.at)}.
                  {c.decision.reason ? ` Reason: “${c.decision.reason}”.` : ''} Status is now {status(c.status).toLowerCase()}.
                </p>
              ) : canDecide ? (
                <div className="space-y-3">
                  {needsSupervisor && <Notice>This needs a supervisor. Sign in as a supervisor to approve, or override with a reason.</Notice>}
                  <label className="block">
                    <span className="text-[13.5px] text-ink-2">Reason (needed to override)</span>
                    <input value={reason} onChange={(e) => setReason(e.target.value)} className="field mt-1" />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={busy || needsSupervisor} onClick={() => decide(Object.keys(edits).length ? 'edit' : 'approve')}>
                      {Object.keys(edits).length ? 'Approve with my edits' : 'Approve'}
                    </Button>
                    <Button tone="danger" disabled={busy || !reason.trim()} onClick={() => decide('override')}>Override</Button>
                  </div>
                  <p className="text-[12.5px] text-ink-3">Ferot never moves money. An authorised upay officer carries out an approved hold (MFS Regulations 2022, §12.3).</p>
                </div>
              ) : (
                <p className="text-[14px] text-ink-3">Your role ({session.role}) can view this case but not decide it.</p>
              )}
              {error && <div className="mt-3"><Notice tone="signal">{error}</Notice></div>}
              {session.role === 'compliance' && (
                <div className="mt-4 pt-4 border-t border-line space-y-2">
                  <p className="text-[13.5px] text-ink-2">Export the evidence pack for a verified request, such as a police GD (MFS Regulations 2022, §18.2).</p>
                  <div className="flex gap-2">
                    <input value={exportRef} onChange={(e) => setExportRef(e.target.value)} placeholder="Request reference" className="field" />
                    <Button tone="secondary" disabled={exportRef.trim().length < 3} onClick={async () => {
                      const data = await api.exportCase(c.case_id, exportRef)
                      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
                      const a = document.createElement('a'); a.href = url; a.download = `${c.case_id}-evidence.json`; a.click()
                      load()
                    }}>Export</Button>
                  </div>
                </div>
              )}
            </div>
          </Panel>

          {Object.keys(c.drafts).length > 0 && (
            <Panel title="Drafted replies" kind="generated" aside={
              <div role="radiogroup" aria-label="Language" className="inline-flex rounded-md bg-paper-2 p-0.5 text-[13px]">
                {(['en', 'bn'] as const).map((l) => (
                  <button key={l} role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className={`px-2.5 py-0.5 rounded ${lang === l ? 'bg-surface shadow-sm font-medium' : 'text-ink-2'}`}>{l === 'en' ? 'English' : 'বাংলা'}</button>
                ))}
              </div>}>
              <div className="flex flex-wrap gap-1.5 mb-3" role="tablist">
                {Object.keys(c.drafts).map((k) => (
                  <button key={k} role="tab" aria-selected={draftId === k} onClick={() => setDraftId(k)}
                    className={`text-[13.5px] px-3 py-1 rounded-full border ${draftId === k ? 'bg-ink text-paper border-ink' : 'border-line text-ink-2 hover:border-ink-3'}`}>
                    {DRAFT_NAMES[k] ?? k}
                  </button>
                ))}
              </div>
              {draft && (
                <>
                  <textarea value={draftText} onChange={(e) => setEdits({ ...edits, [draftId]: { ...edits[draftId], [lang]: e.target.value } })}
                    rows={6} lang={lang} className="field leading-relaxed text-[14.5px]" disabled={!canDecide} aria-label="Draft text" />
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
                    {draft.audience !== 'internal' && <Check ok={draft.checks.passed}>Grounded in case facts</Check>}
                    {draft.audience !== 'internal' && <Check ok={draft.checks.passed}>No refund promise</Check>}
                    {draft.audience === 'recipient' && <Check ok={draft.checks.passed}>No tipping off</Check>}
                    <span className="text-ink-3">Source: {draft.source}</span>
                  </div>
                </>
              )}
            </Panel>
          )}

          {c.intended.found && c.intended.candidate && (
            <Panel title="The number they meant" kind="prediction">
              <NumberDiff intended={revealed?.intended ?? c.intended.candidate} actual={revealed?.recipient ?? String(f.recipient)} positions={c.intended.positions ?? []} revealed={!!revealed} />
              <p className="mt-3 text-[13.5px] text-ink-2">Paid {c.intended.count} times before. Keypad distance {c.intended.distance}.</p>
            </Panel>
          )}

          <Panel title="Ledger facts" kind="facts">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[14.5px]">
              <div><dt className="text-[12.5px] text-ink-3">Transfer</dt><dd className="num">{taka(Number(f.amount))}, {f.transfer_ts ? when(String(f.transfer_ts)) : '—'}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">To</dt><dd className="num">{recipient}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Earlier transfers to it</dt><dd className="num">{String(f.earlier_transfers_to_recipient ?? '—')}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Moved out since</dt><dd className="num">{taka(Number(f.outflow_since_transfer ?? 0))}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Others complained</dt><dd className="num">{String(f.other_complainants_on_recipient ?? 0)}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Already sent back</dt><dd>{f.return_flow ? 'Yes' : 'No'}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Transfer status</dt><dd>{f.status ? String(f.status)[0].toUpperCase() + String(f.status).slice(1) : '—'}</dd></div>
              <div><dt className="text-[12.5px] text-ink-3">Cash-out limit left today</dt><dd className="num">{taka(Number(f.remaining_cashout_limit_today ?? 0))}</dd></div>
            </dl>
          </Panel>

          <Panel title="Audit trail" kind="facts" aside={<span className="text-[12.5px] text-ink-3">Hash-chained</span>}>
            <AuditList entries={c.audit ?? []} />
          </Panel>
        </div>
      </div>
    </div>
  )
}
