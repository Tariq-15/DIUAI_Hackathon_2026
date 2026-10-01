import { useCallback, useEffect, useState } from 'react'
import { api, getSession, type QueueRow, type Role, setSession } from '../api'
import { Button, SlaChip, TypeBadge } from '../components'
import { pct, taka, when } from '../lib'

const ROLES: { role: Role; label: string; note: string }[] = [
  { role: 'agent', label: 'Agent', note: 'Approves most recommendations' },
  { role: 'supervisor', label: 'Supervisor', note: 'Approves rejections; can reset the demo' },
  { role: 'analyst', label: 'Analyst', note: 'Clusters, KPIs, reports' },
  { role: 'compliance', label: 'Compliance', note: 'AML queue; exports on a verified request' },
]

export function SignIn({ onDone }: { onDone: () => void }) {
  const [actor, setActor] = useState('tania')
  const [role, setRole] = useState<Role>('agent')
  return (
    <div className="max-w-md mx-auto mt-16 bg-white rounded-xl ring-1 ring-slate-200 p-6">
      <h2 className="text-lg font-semibold">Sign in (demo)</h2>
      <p className="text-xs text-slate-500 mt-1">Prototype only. In production, identity and role come from upay's single sign-on.</p>
      <label className="block text-sm mt-4">Name</label>
      <input value={actor} onChange={(e) => setActor(e.target.value)} className="w-full rounded-lg ring-1 ring-slate-300 px-3 py-2 mt-1" />
      <div className="mt-4 space-y-2">
        {ROLES.map((r) => (
          <label key={r.role} className={`flex items-start gap-2 p-2 rounded-lg ring-1 cursor-pointer ${role === r.role ? 'ring-teal-600 bg-teal-50' : 'ring-slate-200'}`}>
            <input type="radio" checked={role === r.role} onChange={() => setRole(r.role)} className="mt-1" />
            <span><span className="font-medium text-sm">{r.label}</span><span className="block text-xs text-slate-500">{r.note}</span></span>
          </label>
        ))}
      </div>
      <Button className="w-full mt-4" disabled={!actor.trim()} onClick={() => { setSession({ actor: actor.trim(), role }); onDone() }}>Continue</Button>
    </div>
  )
}

export default function Console({ go }: { go: (to: string) => void }) {
  const [session, setS] = useState(getSession())
  const [rows, setRows] = useState<QueueRow[]>([])
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'open' | 'all'>('open')

  const load = useCallback(() => {
    api.queue().then(setRows).catch((e) => setError(String(e)))
  }, [])
  useEffect(() => {
    if (!session) return
    load()
    const id = window.setInterval(load, 5000)
    return () => window.clearInterval(id)
  }, [session, load])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  const shown = rows.filter((r) => filter === 'all' || ['new', 'human_review'].includes(r.status))

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold">Dispute queue</h1>
        <span className="text-xs text-slate-500">Sorted by taka at risk if the case waits · numbers masked (R9)</span>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <select value={filter} onChange={(e) => setFilter(e.target.value as 'open' | 'all')} className="rounded-lg ring-1 ring-slate-300 px-2 py-1">
            <option value="open">Open cases</option>
            <option value="all">All cases</option>
          </select>
          {session.role === 'supervisor' && (
            <Button tone="secondary" onClick={async () => { await api.reset(); load() }}>Reset demo</Button>
          )}
          <span className="text-slate-600">{session.actor} · {session.role}</span>
          <Button tone="secondary" onClick={() => { setSession(null); setS(null) }}>Sign out</Button>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
      <div className="mt-4 bg-white rounded-xl ring-1 ring-slate-200 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 bg-slate-50">
            <tr>
              <th className="text-left px-3 py-2">At risk if it waits</th>
              <th className="text-left px-3 py-2">Case</th>
              <th className="text-left px-3 py-2">Type (prediction)</th>
              <th className="text-right px-3 py-2">Disputed</th>
              <th className="text-right px-3 py-2">Holdable now</th>
              <th className="text-left px-3 py-2">Deadline (MFS §17.3)</th>
              <th className="text-left px-3 py-2">Recommendation</th>
              <th className="text-left px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.case_id} onClick={() => go(`/console/case/${r.case_id}`)} className="border-t border-slate-100 hover:bg-teal-50/40 cursor-pointer">
                <td className="px-3 py-2">
                  <div className="font-semibold tabular-nums">{taka(r.lost_by_waiting)}</div>
                  <div className="text-xs text-slate-400">score {Math.round(r.priority)}</div>
                </td>
                <td className="px-3 py-2">
                  <div className="font-medium">{r.case_id}</div>
                  <div className="text-xs text-slate-500">{when(r.created_at)} · {r.channel} · {r.language} · to …{r.recipient_last4}</div>
                </td>
                <td className="px-3 py-2"><TypeBadge type={r.case_type} label={r.label} /> <span className="text-xs text-slate-500">{pct(r.confidence)}</span></td>
                <td className="px-3 py-2 text-right tabular-nums">{taka(r.amount)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{taka(r.recoverable_now)}</td>
                <td className="px-3 py-2"><SlaChip sla={r.sla} /></td>
                <td className="px-3 py-2 text-xs"><span className="font-mono">{r.rule_id}</span><div className="text-slate-500">needs {r.approval}</div></td>
                <td className="px-3 py-2 text-xs">{r.status.replace('_', ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!shown.length && <p className="p-6 text-sm text-slate-500">No cases. Submit one from the customer app.</p>}
      </div>
    </div>
  )
}
