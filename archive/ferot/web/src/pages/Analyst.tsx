import { useEffect, useState } from 'react'
import { api, getSession, type GuardAlert } from '../api'
import { Button, Notice, Panel, Stat } from '../components'
import { taka, TYPE_LABEL, TYPE_TONE, useWidth, when } from '../lib'
import { SignIn, UserChip } from './Console'

type Any = Record<string, any>

const SLICE_NAMES: Record<string, string> = { language: 'Language', channel: 'Channel', age_band: 'Age', area: 'Area', kyc: 'KYC level' }
const GROUP_NAMES: Record<string, string> = { bn: 'Bangla', en: 'English', banglish: 'Banglish', app: 'App', call: 'Phone call', ussd: 'USSD', rural: 'Rural', urban: 'Urban', full: 'Full KYC', limited: 'Limited KYC' }
const POLICIES: [string, string][] = [
  ['largest', 'Largest amount first'], ['ferot', 'Ferot priority'], ['ferot_fast', 'Ferot, with faster handling*'], ['oracle', 'Ceiling: knows the future'],
]
const SHORT: Record<string, string> = { genuine_wrong_send: 'Genuine', scam_victim: 'Scam', double_recovery: 'Double', false_claim: 'False', technical_failure: 'Technical' }

function Bar({ value, max = 1, tone = '#c4d0cb' }: { value: number; max?: number; tone?: string }) {
  return (
    <div className="h-2 bg-paper-2 rounded-full overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${Math.max((value / max) * 100, 1)}%`, background: tone }} />
    </div>
  )
}

function SimChart({ sum }: { sum: Any }) {
  const [ref, W] = useWidth(560)
  const rows = POLICIES.filter(([k]) => sum[k])
  const max = Math.max(...rows.map(([k]) => sum[k].gain_vs_fcfs_ci95?.[1] ?? sum[k].gain_vs_fcfs), 1) * 1.08
  const labelW = W < 480 ? 0 : 190
  const H = rows.length * 46 + 34
  const x = (v: number) => labelW + (v / max) * (W - labelW - 70)
  return (
    <div ref={ref}>
      <svg width={W} height={H} role="img" aria-label="Extra taka recovered versus first come, first served, with 95% confidence intervals">
        <line x1={x(0)} x2={x(0)} y1={0} y2={H - 26} stroke="#0f2a24" />
        <text x={x(0)} y={H - 8} fontSize="12" fill="#6b7f78" textAnchor="middle">First come, first served</text>
        {rows.map(([k, label], i) => {
          const r = sum[k]
          const yy = i * 46 + 22
          const [lo, hi] = r.gain_vs_fcfs_ci95 ?? [r.gain_vs_fcfs, r.gain_vs_fcfs]
          const tone = k === 'ferot' ? '#006a4e' : k === 'oracle' ? '#a9bdb6' : k === 'ferot_fast' ? '#3f9a7a' : '#3e554e'
          return (
            <g key={k}>
              {labelW > 0 && <text x={0} y={yy + 4} fontSize="13.5" fill="#0f2a24" fontWeight={k === 'ferot' ? 600 : 400}>{label}</text>}
              {labelW === 0 && <text x={x(0) + 4} y={yy - 9} fontSize="12" fill="#3e554e">{label}</text>}
              <line x1={x(0)} x2={x(r.gain_vs_fcfs)} y1={yy} y2={yy} stroke={tone} strokeWidth="6" strokeOpacity="0.22" strokeLinecap="round" />
              <line x1={x(lo)} x2={x(hi)} y1={yy} y2={yy} stroke={tone} strokeWidth="2" />
              <line x1={x(lo)} x2={x(lo)} y1={yy - 5} y2={yy + 5} stroke={tone} strokeWidth="2" />
              <line x1={x(hi)} x2={x(hi)} y1={yy - 5} y2={yy + 5} stroke={tone} strokeWidth="2" />
              <circle cx={x(r.gain_vs_fcfs)} cy={yy} r="5" fill={tone} />
              <text x={x(hi) + 8} y={yy + 4} fontSize="13" fill="#0f2a24" className="num">+{taka(r.gain_vs_fcfs)} ({r.gain_vs_fcfs_pct}%)</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function Confusion({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const max = Math.max(...matrix.flat(), 1)
  return (
    <div className="overflow-x-auto">
      <table className="text-[13px] border-separate border-spacing-[3px]">
        <thead>
          <tr>
            <th className="text-left font-normal text-ink-3 pr-2">True ↓ / predicted →</th>
            {labels.map((l) => <th key={l} className="font-medium text-ink-2 px-1 w-16">{SHORT[l] ?? l}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={labels[i]}>
              <th className="text-left font-medium text-ink-2 pr-2 whitespace-nowrap">{SHORT[labels[i]] ?? labels[i]}</th>
              {row.map((v, j) => {
                const strength = v / max
                const diag = i === j
                return (
                  <td key={j} className="num text-center rounded-md h-9 w-16"
                    style={{ background: v === 0 ? '#f4f7f5' : diag ? `rgba(0,106,78,${0.12 + strength * 0.8})` : `rgba(215,38,61,${0.15 + strength * 2.5})`, color: diag && strength > 0.5 ? '#fff' : '#0f2a24' }}>
                    {v}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Analyst({ go }: { go: (to: string) => void }) {
  const [session, setS] = useState(getSession())
  const [kpis, setKpis] = useState<Any | null>(null)
  const [metrics, setMetrics] = useState<Any | null>(null)
  const [sim, setSim] = useState<Any | null>(null)
  const [clusters, setClusters] = useState<Any[] | null>(null)
  const [aml, setAml] = useState<Any[] | null>(null)
  const [alerts, setAlerts] = useState<GuardAlert[] | null>(null)
  const [slice, setSlice] = useState('channel')

  useEffect(() => {
    if (!session) return
    api.kpis().then(setKpis).catch(() => {})
    api.metrics().then(setMetrics).catch(() => {})
    api.simulation().then(setSim).catch(() => {})
    api.clusters().then(setClusters).catch(() => setClusters(null))
    api.amlQueue().then(setAml).catch(() => setAml(null))
    api.guardAlerts().then(setAlerts).catch(() => setAlerts(null))
  }, [session])

  if (!session) return <SignIn onDone={() => setS(getSession())} />
  const m4 = metrics?.m4_classifier
  const base = metrics?.m4_baselines
  const alert = metrics?.m4_alerting
  const guard = metrics?.guard
  const fair = metrics?.fairness
  const m5 = metrics?.m5_recoverability
  const sum = sim?.summary

  return (
    <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-8">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[32px] font-semibold">Evidence</h1>
          <p className="text-[14.5px] text-ink-2 mt-1 max-w-[46rem]">
            How well each model works on held-out data, where it fails, and whether it treats customers fairly.
            The test set is the last 15 days of the synthetic ledger; nothing from those days was used in training.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          <Button tone="secondary" size="sm" onClick={async () => {
            const csv = await api.report()
            const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
            const a = document.createElement('a'); a.href = url; a.download = 'dispute-report.csv'; a.click()
          }}>Download dispute report</Button>
          <UserChip onOut={() => setS(null)} />
        </div>
      </div>

      {metrics && (
        <div className="mt-6">
          <Notice>
            <b>Read these numbers with care.</b> The data is synthetic, and its scam pattern is cleaner than real fraud, which is why some scores
            sit near 1.0. They show the method works end to end, not how it will score on upay's records. The failures below matter more.
          </Notice>
        </div>
      )}

      {alert && guard && (
        <section className="mt-8">
          <h2 className="text-[22px] font-semibold">Catching scams</h2>
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel title="Before the send: Ferot Guard" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">{guard.test_transfers.toLocaleString('en-US')} test transfers, {guard.test_scams} scams</span>}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                <Stat label="PR-AUC" value={guard.pr_auc.toFixed(guard.pr_auc >= 0.999 ? 4 : 3)} note={`Scam share ${(guard.scam_share * 100).toFixed(1)}%`} />
                <Stat label="Scam sends warned" value={`${(guard.recall_at_warn * 100).toFixed(1)}%`} note="Recall at the warn band" />
                <Stat label="Warnings that were scams" value={`${(guard.precision_at_warn * 100).toFixed(1)}%`} note="Precision at the warn band" />
                <Stat label="Ordinary sends warned" value={guard.innocent_warned_per_100} note="Per 100 innocent transfers" />
                <Stat label="Ordinary sends paused" value={guard.innocent_reviewed_per_100} note="Per 100, the 30-second pause" />
                <Stat label="Typos caught" value={`${Math.round(guard.typo_caught_rate * 100)}%`} note="“Did you mean” check" />
              </div>
              <p className="mt-4 text-[13px] text-ink-3">
                LightGBM on transfer features, fused with an IsolationForest anomaly score; validation chose weight {guard.fusion.w_model} for the model.
                Warn and pause bands are the 99th and 99.9th percentile of ordinary transfers in validation.
              </p>
            </Panel>
            <Panel title="After the complaint: hold decision" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">{alert.victim_cases} victim cases</span>}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                <Stat label="Scam PR-AUC" value={alert.scam_pr_auc.toFixed(alert.scam_pr_auc >= 0.999 ? 4 : 3)} />
                <Stat label="Scams held" value={`${(alert.scam_recall_at_policy * 100).toFixed(1)}%`} note={`Recall at P(scam) ≥ ${alert.policy_threshold}`} />
                <Stat label="Holds that were scams" value={`${(alert.scam_precision_at_policy * 100).toFixed(0)}%`} note="Precision at the threshold" />
                <Stat label="False alarm rate" value={`${(alert.false_alarm_rate_non_scam * 100).toFixed(1)}%`} note="Non-scam cases flagged" />
                <Stat label="Wrongful rejections" value={alert.wrongful_rejections} note="Real victims told no" tone={alert.wrongful_rejections ? '#d7263d' : undefined} />
              </div>
              <p className="mt-4 text-[13px] text-ink-3">{alert.note} The threshold was lowered from 0.60 to 0.45: missing a scam costs the customer the money, while a wrong hold is capped and reviewed by a person.</p>
            </Panel>
          </div>
        </section>
      )}

      {m4 && base && (
        <section className="mt-10 grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Panel title="Does the machine learning matter?" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">Macro-F1, 5 case types</span>}>
            <table className="w-full text-[14px]">
              <tbody>
                {[
                  ['Ferot case classifier', m4.macro_f1, '#006a4e'],
                  ['Without wallet-network features', base.without_graph_features, '#7fa99b'],
                  ['Without text features', base.without_text_features, '#7fa99b'],
                  ['Text-only model', base.text_only_model, '#c4d0cb'],
                  ['Keyword rules', base.keyword_rules_macro_f1, '#c4d0cb'],
                ].map(([k, v, tone]) => (
                  <tr key={k as string} className="border-b border-line-2 last:border-0">
                    <td className={`py-2 pr-3 ${k === 'Ferot case classifier' ? 'font-semibold' : ''}`}>{k}</td>
                    <td className="w-[45%]"><Bar value={v as number} tone={tone as string} /></td>
                    <td className="num text-right w-14">{(v as number).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[13.5px] text-ink-2">
              Text alone cannot tell a typo from a false claim; the ledger can. Dropping the text features changes little,
              so the ledger does most of the work. Scam recall {m4.per_class.scam_victim.recall}; recall on job-offer scams never seen
              in training {m4.held_out_job_offer_scam_recall}. Calibration error (ECE) {m4.ece}.
            </p>
          </Panel>
          {m4.confusion_matrix && (
            <Panel title="Where the classifier is wrong" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">{metrics?.data?.test} test cases</span>}>
              <Confusion labels={m4.confusion_matrix.labels} matrix={m4.confusion_matrix.matrix} />
              <p className="mt-3 text-[13.5px] text-ink-2">
                Green is right, red is wrong. Most errors are scam victims read as another type: the victim “returned” money to a wallet that
                looks ordinary. These cases still reach a person, because the hold rule and the human approval do not depend on the label alone.
              </p>
            </Panel>
          )}
        </section>
      )}

      {sum && (
        <section className="mt-10">
          <Panel title="Does the queue order recover more money?" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">{sim.cases} held-out cases, {sim.assumptions.seeds} runs</span>}>
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-8 items-start">
              <SimChart sum={sum} />
              <div className="text-[14px] text-ink-2 space-y-2">
                <p>First come, first served recovers <b className="num text-ink">{taka(sum.fcfs.recovered_mean)}</b> with {sim.assumptions.agents} agents working Sunday to Thursday, 09:00 to 17:00.</p>
                <p>Ferot's order adds <b className="num text-ink">{taka(sum.ferot.gain_vs_fcfs)}</b>. A simple largest-amount-first rule adds about the same on this data, so ordering alone is a modest gain.</p>
                <p>The bigger lever is speed: a ready-made case file lets an agent act sooner. *That run assumes handling time halves; we have not measured it.</p>
              </div>
            </div>
          </Panel>
        </section>
      )}

      {fair && (
        <section className="mt-10 grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-6 items-start">
          <Panel title="Is it fair across customers?" kind="prediction" aside={
            <label className="text-[13px] text-ink-2 inline-flex items-center gap-2">Group by
              <select value={slice} onChange={(e) => setSlice(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1 text-[13.5px]">
                {Object.keys(fair).map((k) => <option key={k} value={k}>{SLICE_NAMES[k] ?? k}</option>)}
              </select>
            </label>}>
            <table className="w-full text-[14px]">
              <thead>
                <tr className="text-left text-[12.5px] text-ink-3 border-b border-line">
                  <th className="font-medium py-2">Group</th><th className="font-medium text-right">Cases</th>
                  <th className="font-medium text-right">Accuracy</th><th className="font-medium text-right">Scam recall</th><th className="font-medium text-right">Wrongful rejections</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(fair[slice].groups as Record<string, Any>).map(([g, v]) => (
                  <tr key={g} className="border-b border-line-2 last:border-0">
                    <td className="py-2">{GROUP_NAMES[g] ?? g}</td>
                    <td className="num text-right text-ink-3">{v.n}</td>
                    <td className="num text-right">{(v.accuracy * 100).toFixed(1)}%</td>
                    <td className="num text-right">{v.scam_recall === null || v.scam_recall === undefined ? '—' : `${(v.scam_recall * 100).toFixed(1)}%`}</td>
                    <td className="num text-right">{(v.wrongful_rejection_rate * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[13.5px] text-ink-2">
              Largest accuracy gap by {(SLICE_NAMES[slice] ?? slice).toLowerCase()}: <b className="num">{(fair[slice].max_accuracy_gap * 100).toFixed(1)} points</b>.
              {slice === 'channel' && ' Phone complaints are harder because people describe the transfer less exactly; agents should confirm the TrxID on calls.'}
            </p>
          </Panel>
          {guard?.fairness && (
            <Panel title="Guard false warnings by group" kind="prediction">
              <div className="space-y-4">
                {Object.entries(guard.fairness as Record<string, Record<string, Any>>).map(([s, groups]) => {
                  const max = Math.max(...Object.values(groups).map((v) => v.innocent_warned_per_100), 1)
                  return (
                    <div key={s}>
                      <h4 className="text-[13.5px] font-semibold text-ink-2">{SLICE_NAMES[s] ?? s}</h4>
                      <div className="mt-1.5 space-y-1.5">
                        {Object.entries(groups).map(([g, v]) => (
                          <div key={g} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-3 text-[13.5px]">
                            <span>{GROUP_NAMES[g] ?? g}</span>
                            <Bar value={v.innocent_warned_per_100} max={max} tone="#e3a008" />
                            <span className="num text-right">{v.innocent_warned_per_100}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 text-[13px] text-ink-3">Ordinary transfers warned, per 100. USSD users see about twice the false warnings of app users; it is still under 1 in 100.</p>
            </Panel>
          )}
        </section>
      )}

      {m5 && (
        <section className="mt-10">
          <Panel title="Is the recoverability estimate better than today's balance?" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">Brier score, lower is better</span>}>
            <div className="overflow-x-auto">
              <table className="w-full text-[14px] min-w-[520px]">
                <thead>
                  <tr className="text-left text-[12.5px] text-ink-3 border-b border-line">
                    <th className="font-medium py-2">Horizon</th><th className="font-medium text-right">Ferot model</th>
                    <th className="font-medium text-right">“Balance now” rule</th><th className="font-medium text-right">AUC</th><th className="font-medium text-right">Winner</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(m5 as Record<string, Any>).map(([h, v]) => {
                    const mins = parseInt(h)
                    const better = v.brier_model < v.brier_baseline_balance_now
                    return (
                      <tr key={h} className="border-b border-line-2 last:border-0">
                        <td className="py-2">{mins < 1440 ? `${mins / 60} h` : `${mins / 1440} ${mins === 1440 ? 'day' : 'days'}`}</td>
                        <td className="num text-right font-medium">{v.brier_model.toFixed(3)}</td>
                        <td className="num text-right">{v.brier_baseline_balance_now.toFixed(3)}</td>
                        <td className="num text-right">{v.auc_model.toFixed(2)}</td>
                        <td className={`text-right ${better ? 'text-flag' : 'text-signal-2'}`}>{better ? 'Model' : 'Rule'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[13.5px] text-ink-2">At one hour, today's balance is a slightly better guess than the model. From six hours on, the model wins, and that is where queue order matters.</p>
          </Panel>
        </section>
      )}

      <section className="mt-12">
        <h2 className="text-[22px] font-semibold">Operations</h2>
        {kpis && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-x-8 gap-y-5 border-y border-line py-5">
            <Stat label="Cases" value={kpis.cases} />
            <Stat label="Open" value={kpis.open} />
            <Stat label="Decided" value={kpis.decided} />
            <Stat label="Overridden" value={`${Math.round((kpis.override_rate ?? 0) * 100)}%`} note="Of decided cases" />
            <Stat label="Holds requested" value={taka(kpis.holds_requested_total)} tone="#006a4e" />
            <Stat label="Audit chain" value={kpis.audit_chain?.ok ? 'Intact' : 'Broken'} tone={kpis.audit_chain?.ok ? '#006a4e' : '#d7263d'} note="Hash chain re-verified" />
          </div>
        )}
        {kpis?.by_type && (
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[14px]">
            {Object.entries(kpis.by_type as Record<string, number>).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: TYPE_TONE[k] ?? '#a9bdb6' }} />{TYPE_LABEL[k] ?? 'Needs information'} <span className="num text-ink-3">{v}</span></span>
            ))}
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Panel title="Wallets many customers complained about" kind="prediction" aside={<span className="text-[12.5px] text-ink-3">Mule clusters, M7</span>}>
            {clusters ? (
              clusters.length ? (
                <table className="w-full text-[14px]">
                  <thead><tr className="text-left text-[12.5px] text-ink-3 border-b border-line"><th className="font-medium py-2">Linked wallets</th><th className="font-medium text-right">Complainants</th><th className="font-medium text-right">Cash-out agents</th><th className="font-medium pl-4">First seen</th></tr></thead>
                  <tbody>
                    {clusters.slice(0, 8).map((c, i) => (
                      <tr key={i} className="border-b border-line-2 last:border-0">
                        <td className="py-2 num text-[13.5px]">{c.wallets.slice(0, 3).map((w: string) => `•••• ${w.slice(-4)}`).join(', ')}{c.wallets.length > 3 ? ` and ${c.wallets.length - 3} more` : ''}</td>
                        <td className="num text-right">{c.complainants}</td>
                        <td className="num text-right">{c.cash_out_agents}</td>
                        <td className="pl-4 text-[13px] text-ink-2">{when(c.first_seen)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="text-ink-3">No clusters yet.</p>
            ) : <p className="text-ink-3">Sign in as an analyst, supervisor or compliance officer to see clusters.</p>}
            <p className="mt-3 text-[13px] text-ink-3">Flags go to upay's AML/CFT team, which decides any report to BFIU. Nothing is said to the wallet holders (MLPA 2012, §6).</p>
          </Panel>

          <div className="space-y-6">
            <Panel title="AML review queue" kind="facts">
              {aml ? (
                aml.length ? (
                  <ul className="space-y-2 text-[14px]">
                    {aml.map((a) => (
                      <li key={a.id} className="flex flex-wrap items-baseline gap-x-3">
                        <button className="link num" onClick={() => go(`/console/case/${a.case_id}`)}>{a.case_id}</button>
                        <span>{a.role === 'recipient' ? 'Receiving wallet' : 'Claimant'} <span className="num">•••• {a.wallet.slice(-4)}</span></span>
                        <span className="text-ink-3 text-[13px] ml-auto">{when(a.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-ink-3">Empty. Approving a scam or double-recovery case adds the wallet here.</p>
              ) : <p className="text-ink-3">Sign in as compliance or a supervisor to see the AML queue.</p>}
            </Panel>
            <Panel title="Guard warnings" kind="facts" aside={<span className="text-[12.5px] text-ink-3">Numbers masked</span>}>
              {alerts && alerts.length ? (
                <ul className="space-y-2.5 text-[14px]">
                  {alerts.slice(0, 8).map((a) => (
                    <li key={a.check_id} className="grid grid-cols-[auto_1fr_auto] gap-x-3 items-baseline">
                      <span className={`num font-semibold ${a.band === 'review' ? 'text-signal' : 'text-turmeric-ink'}`}>{a.risk}</span>
                      <span className="min-w-0">
                        <span className="num">{taka(a.amount)}</span> to <span className="num">•••• {a.recipient_last4}</span>
                        <span className="block text-[12.5px] text-ink-3 truncate">{a.reasons[0] ?? ''}</span>
                      </span>
                      <span className="text-[13px] text-ink-2">{{ cancelled: 'Cancelled', sent_anyway: 'Sent anyway', changed_number: 'Changed number' }[a.decision ?? ''] ?? 'No answer yet'}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-ink-3">No warnings yet. Try the risky transfers in the customer app.</p>}
            </Panel>
          </div>
        </div>
      </section>
    </div>
  )
}
