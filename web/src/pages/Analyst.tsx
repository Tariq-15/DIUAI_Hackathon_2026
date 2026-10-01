import { useEffect, useState } from 'react'
import { api, getSession } from '../api'
import { Button, Card } from '../components'
import { taka, TYPE_LABEL, when } from '../lib'
import { SignIn } from './Console'

type Any = Record<string, any>

export default function Analyst() {
  const [session, setS] = useState(getSession())
  const [kpis, setKpis] = useState<Any | null>(null)
  const [metrics, setMetrics] = useState<Any | null>(null)
  const [sim, setSim] = useState<Any | null>(null)
  const [clusters, setClusters] = useState<Any[] | null>(null)
  const [aml, setAml] = useState<Any[] | null>(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!session) return
    api.kpis().then(setKpis).catch(() => {})
    api.metrics().then(setMetrics).catch(() => {})
    api.simulation().then(setSim).catch(() => {})
    api.clusters().then(setClusters).catch((e) => setNote(String(e)))
    api.amlQueue().then(setAml).catch(() => setAml(null))
  }, [session])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  const m4 = metrics?.m4_classifier
  const base = metrics?.m4_baselines
  const sum = sim?.summary

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Analyst & evidence</h1>
        <span className="text-xs text-slate-500">signed in as {session.actor} ({session.role})</span>
        <Button tone="secondary" className="ml-auto" onClick={async () => {
          const csv = await api.report()
          const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
          const a = document.createElement('a'); a.href = url; a.download = 'dispute-report.csv'; a.click()
        }}>Download dispute report (MFS §16.3)</Button>
      </div>
      {note && <p className="text-xs text-amber-700">{note}</p>}

      {kpis && (
        <div className="grid sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            ['Cases', kpis.cases], ['Open', kpis.open], ['Decided', kpis.decided],
            ['Override rate', `${Math.round((kpis.override_rate ?? 0) * 100)}%`],
            ['Holdable now', taka(kpis.recoverable_now_total)], ['Audit chain', kpis.audit_chain?.ok ? 'intact ✓' : 'BROKEN'],
          ].map(([k, v]) => (
            <div key={k as string} className="bg-white rounded-xl ring-1 ring-slate-200 p-3">
              <div className="text-xs text-slate-500">{k}</div>
              <div className="text-lg font-semibold">{String(v)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Does the AI matter? Case-type classifier (held-out days 75-90)" tag="prediction">
          {m4 && base ? (
            <>
              <table className="w-full text-sm">
                <tbody>
                  {[
                    ['Ferot M4 (ledger + text)', m4.macro_f1],
                    ['Without graph features', base.without_graph_features],
                    ['Without text features', base.without_text_features],
                    ['Text-only model', base.text_only_model],
                    ['Keyword rules', base.keyword_rules_macro_f1],
                  ].map(([k, v]) => (
                    <tr key={k as string} className="border-t border-slate-100">
                      <td className="py-1.5">{k}</td>
                      <td className="w-1/2"><div className="h-2 bg-slate-100 rounded"><div className={`h-2 rounded ${k === 'Ferot M4 (ledger + text)' ? 'bg-indigo-600' : 'bg-slate-400'}`} style={{ width: `${(v as number) * 100}%` }} /></div></td>
                      <td className="text-right tabular-nums w-14">{(v as number).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-slate-600 mt-2">Macro-F1. Scam recall {m4.per_class.scam_victim.recall}; recall on a scam type never seen in training (job offers): {m4.held_out_job_offer_scam_recall}. Calibration error (ECE) {m4.ece}. Text alone cannot tell a genuine typo from a false claim; the ledger can.</p>
            </>
          ) : <p className="text-sm text-slate-500">Run training to see metrics.</p>}
        </Card>

        <Card title="Queue simulation: money still holdable when an agent acts" tag="prediction">
          {sum ? (
            <>
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500"><tr><th className="text-left">Policy</th><th className="text-right">Recovered</th><th className="text-right">vs first-come</th><th className="text-right">Median wait</th></tr></thead>
                <tbody>
                  {[['fcfs', 'First come, first served'], ['largest', 'Largest amount first'], ['ferot', 'Ferot priority'], ['ferot_fast', 'Ferot + faster handling*'], ['oracle', 'Oracle ceiling (knows the future)']].map(([k, label]) => sum[k] && (
                    <tr key={k} className={`border-t border-slate-100 ${k === 'ferot' ? 'font-semibold' : ''}`}>
                      <td className="py-1.5">{label}</td>
                      <td className="text-right tabular-nums">{taka(sum[k].recovered_mean)}</td>
                      <td className="text-right tabular-nums">{sum[k].gain_vs_fcfs_pct !== undefined ? `+${sum[k].gain_vs_fcfs_pct}%` : '—'}</td>
                      <td className="text-right tabular-nums">{Math.round(sum[k].median_minutes_to_action / 60)} h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-slate-600 mt-2">{sim.cases} held-out cases, {sim.assumptions.agents} agents working Sun-Thu 09:00-17:00, {sim.assumptions.seeds} runs. Ferot gain 95% CI {sum.ferot?.gain_vs_fcfs_ci95?.map((x: number) => taka(x)).join(' to ')}. *Assumes a pre-built case file halves handling time; not measured.</p>
            </>
          ) : <p className="text-sm text-slate-500">Run the simulation to see results.</p>}
        </Card>

        <Card title="Mule clusters (M7): wallets many customers complained about" tag="prediction">
          {clusters ? (
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-500"><tr><th className="text-left">Wallets</th><th className="text-right">Complainants</th><th className="text-right">Cash-out agents</th><th className="text-left pl-3">First seen</th></tr></thead>
              <tbody>
                {clusters.slice(0, 10).map((c, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="py-1.5 font-mono text-xs">{c.wallets.map((w: string) => `…${w.slice(-4)}`).join(', ')}</td>
                    <td className="text-right">{c.complainants}</td>
                    <td className="text-right">{c.cash_out_agents}</td>
                    <td className="pl-3 text-xs">{when(c.first_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-sm text-slate-500">Analyst, supervisor or compliance role needed.</p>}
          <p className="text-xs text-slate-500 mt-2">Flags go to upay's AML/CFT team, which decides any report to BFIU. Nothing is said to the wallet holders (MLPA §6).</p>
        </Card>

        <Card title="AML review queue" tag="facts">
          {aml ? (
            aml.length ? (
              <ul className="text-sm space-y-1">{aml.map((a) => <li key={a.id}>{a.case_id} · {a.role} …{a.wallet.slice(-4)} · {when(a.created_at)}</li>)}</ul>
            ) : <p className="text-sm text-slate-500">Empty. Approve a scam or double-recovery case to add one.</p>
          ) : <p className="text-sm text-slate-500">Compliance or supervisor role needed.</p>}
          {kpis?.by_type && (
            <div className="mt-3 text-xs text-slate-600">
              Cases by type: {Object.entries(kpis.by_type).map(([k, v]) => `${TYPE_LABEL[k] ?? k} ${v}`).join(' · ')}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
