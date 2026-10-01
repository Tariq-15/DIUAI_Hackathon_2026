import { useCallback, useEffect, useState } from 'react'
import { api, getSession, type QueueRow, type Role, setSession } from '../api'
import { Button, SlaText, Stat, TypeMark } from '../components'
import { day, taka, when } from '../lib'
import { CHANNEL, LANGUAGE, OPEN, status } from '../lib-labels'

const ROLES: { role: Role; label: string; note: string }[] = [
  { role: 'agent', label: 'Agent', note: 'Works the queue and approves most recommendations' },
  { role: 'supervisor', label: 'Supervisor', note: 'Approves rejections and can reset the demo' },
  { role: 'analyst', label: 'Analyst', note: 'Sees clusters, reports and model evidence' },
  { role: 'compliance', label: 'Compliance', note: 'Works the AML queue and exports evidence on a verified request' },
]

export function SignIn({ onDone }: { onDone: () => void }) {
  const [actor, setActor] = useState('tania')
  const [role, setRole] = useState<Role>('agent')
  return (
    <div className="max-w-[440px] mx-auto px-4 pt-16">
      <h1 className="text-[30px] font-semibold">Sign in to the console</h1>
      <p className="mt-2 text-[14.5px] text-ink-2">Demo sign-in. In production, identity and role come from upay's single sign-on.</p>
      <form className="mt-6 space-y-5" onSubmit={(e) => { e.preventDefault(); if (actor.trim()) { setSession({ actor: actor.trim(), role }); onDone() } }}>
        <label className="block">
          <span className="text-[14px] font-medium">Your name</span>
          <input value={actor} onChange={(e) => setActor(e.target.value)} className="field mt-1" autoComplete="off" />
        </label>
        <fieldset>
          <legend className="text-[14px] font-medium">Role</legend>
          <div className="mt-2 space-y-2">
            {ROLES.map((r) => (
              <label key={r.role} className={`flex items-start gap-3 rounded-xl border px-4 py-3 cursor-pointer transition-colors ${role === r.role ? 'border-flag bg-flag-soft/50' : 'border-line bg-surface hover:border-ink-3'}`}>
                <input type="radio" name="role" checked={role === r.role} onChange={() => setRole(r.role)} className="mt-1.5 accent-[#006a4e]" />
                <span><span className="font-semibold">{r.label}</span><span className="block text-[13.5px] text-ink-3">{r.note}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <Button type="submit" size="lg" className="w-full" disabled={!actor.trim()}>Continue</Button>
      </form>
    </div>
  )
}

export function UserChip({ onOut }: { onOut: () => void }) {
  const s = getSession()
  if (!s) return null
  return (
    <span className="inline-flex items-center gap-2 text-[14px]">
      <span className="w-7 h-7 rounded-full bg-night text-paper grid place-items-center text-[13px] font-semibold uppercase" aria-hidden="true">{s.actor.slice(0, 1)}</span>
      <span>{s.actor}, <span className="text-ink-3">{s.role}</span></span>
      <Button tone="quiet" size="sm" onClick={() => { setSession(null); onOut() }}>Sign out</Button>
    </span>
  )
}

function RiskBar({ value, max }: { value: number; max: number }) {
  return (
    <div className="h-1.5 w-24 bg-paper-2 rounded-full overflow-hidden" aria-hidden="true">
      <div className="h-full rounded-full bg-turmeric" style={{ width: `${Math.max((value / Math.max(max, 1)) * 100, value > 0 ? 4 : 0)}%` }} />
    </div>
  )
}

export default function Console({ go }: { go: (to: string) => void }) {
  const [session, setS] = useState(getSession())
  const [rows, setRows] = useState<QueueRow[]>([])
  const [kpis, setKpis] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'open' | 'all'>('open')
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(() => {
    api.queue().then((r) => { setRows(r); setLoaded(true); setError('') }).catch((e) => setError(String(e.message ?? e)))
    api.kpis().then(setKpis).catch(() => {})
  }, [])
  useEffect(() => {
    if (!session) return
    load()
    const id = window.setInterval(load, 5000)
    return () => window.clearInterval(id)
  }, [session, load])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  const open = rows.filter((r) => OPEN.includes(r.status))
  const shown = filter === 'open' ? open : rows
  const maxRisk = Math.max(...shown.map((r) => r.lost_by_waiting), 1)
  const atRisk = open.reduce((a, r) => a + r.lost_by_waiting, 0)
  const holdable = open.reduce((a, r) => a + r.recoverable_now, 0)
  const dueSoon = open.filter((r) => r.sla.breached || r.sla.working_days_left <= 3).length

  return (
    <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-8">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[32px] font-semibold">Dispute queue</h1>
          <p className="text-[14.5px] text-ink-2 mt-1">Ordered by the money likely to leave while a case waits. Numbers are masked until an agent reveals them.</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          {session.role === 'supervisor' && <Button tone="secondary" size="sm" onClick={async () => { await api.reset(); load() }}>Reset demo</Button>}
          <UserChip onOut={() => setS(null)} />
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-5 gap-x-8 gap-y-5 border-y border-line py-5">
        <Stat label="Open cases" value={open.length} />
        <Stat label="Still holdable in open cases" value={taka(holdable)} tone="#006a4e" />
        <Stat label="At risk if they wait 2 h" value={taka(atRisk)} tone="#a77300" />
        <Stat label="Due within 3 working days" value={dueSoon} tone={dueSoon ? '#d7263d' : undefined} />
        <Stat label="Guard warnings shown" value={kpis?.guard_alerts ?? '—'} note="Before the money left" />
      </div>

      <div className="mt-6 flex items-center gap-3">
        <div role="radiogroup" aria-label="Which cases" className="inline-flex rounded-lg bg-paper-2 p-1">
          {(['open', 'all'] as const).map((k) => (
            <button key={k} role="radio" aria-checked={filter === k} onClick={() => setFilter(k)}
              className={`px-3.5 py-1.5 rounded-md text-[14px] ${filter === k ? 'bg-surface shadow-sm font-medium' : 'text-ink-2'}`}>
              {k === 'open' ? `Open (${open.length})` : `All (${rows.length})`}
            </button>
          ))}
        </div>
        <span className="text-[13px] text-ink-3">Updates every 5 seconds</span>
      </div>
      {error && <p className="mt-3 text-[14px] text-signal-2">{error}</p>}

      {/* wide screens: a ledger-style table */}
      <div className="mt-4 hidden md:block bg-surface border border-line rounded-xl overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr className="text-left text-[12.5px] text-ink-3 border-b border-line bg-paper/60">
              <th className="font-medium px-4 py-2.5">At risk if it waits</th>
              <th className="font-medium px-4 py-2.5">Case</th>
              <th className="font-medium px-4 py-2.5">Type</th>
              <th className="font-medium px-4 py-2.5 text-right">Disputed</th>
              <th className="font-medium px-4 py-2.5 text-right">Holdable now</th>
              <th className="font-medium px-4 py-2.5">Deadline</th>
              <th className="font-medium px-4 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.case_id} tabIndex={0} onClick={() => go(`/console/case/${r.case_id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter') go(`/console/case/${r.case_id}`) }}
                className="border-b border-line-2 last:border-0 hover:bg-paper cursor-pointer focus-visible:bg-paper">
                <td className="px-4 py-3">
                  <div className="num text-[17px] font-semibold">{taka(r.lost_by_waiting)}</div>
                  <RiskBar value={r.lost_by_waiting} max={maxRisk} />
                  {r.priority > r.lost_by_waiting + 1 && <div className="text-[12px] text-turmeric-ink mt-0.5" title="Scam victims and USSD-only customers are moved up the queue">Moved up: vulnerable</div>}
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium num">{r.case_id}</div>
                  <div className="text-[12.5px] text-ink-3">{when(r.created_at)}, {CHANNEL[r.channel] ?? r.channel}{r.language ? `, ${LANGUAGE[r.language] ?? r.language}` : ''}</div>
                </td>
                <td className="px-4 py-3"><TypeMark type={r.case_type} label={r.label} confidence={r.confidence} /></td>
                <td className="px-4 py-3 text-right num">{taka(r.amount)}</td>
                <td className="px-4 py-3 text-right num text-flag font-medium">{taka(r.recoverable_now)}</td>
                <td className="px-4 py-3">
                  <SlaText sla={r.sla} />
                  <div className="text-[12.5px] text-ink-3">{day(r.sla.deadline)}</div>
                </td>
                <td className="px-4 py-3">
                  <div>{status(r.status)}</div>
                  <div className="text-[12.5px] text-ink-3">Rule {r.rule_id}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loaded && !shown.length && <p className="px-4 py-8 text-ink-3">No cases yet. Submit one from the customer app and it appears here.</p>}
      </div>

      {/* narrow screens: one block per case */}
      <ul className="mt-4 md:hidden space-y-3">
        {shown.map((r) => (
          <li key={r.case_id}>
            <button onClick={() => go(`/console/case/${r.case_id}`)} className="w-full text-left bg-surface border border-line rounded-xl px-4 py-3.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="num font-medium">{r.case_id}</span>
                <SlaText sla={r.sla} />
              </div>
              <div className="mt-1.5"><TypeMark type={r.case_type} label={r.label} confidence={r.confidence} /></div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-[12.5px] text-ink-3">
                <div>At risk<div className="num text-[16px] text-ink font-semibold">{taka(r.lost_by_waiting)}</div></div>
                <div>Holdable<div className="num text-[16px] text-flag font-semibold">{taka(r.recoverable_now)}</div></div>
                <div>Disputed<div className="num text-[16px] text-ink">{taka(r.amount)}</div></div>
              </div>
            </button>
          </li>
        ))}
        {loaded && !shown.length && <li className="text-ink-3">No cases yet. Submit one from the customer app and it appears here.</li>}
      </ul>
    </div>
  )
}
