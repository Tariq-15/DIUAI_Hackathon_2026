import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { AuditEntry, CurvePoint, DrainPoint, Network, Reason, Sla, TrailStep } from './api'
import { clock, mask, taka, TYPE_LABEL, TYPE_TONE, useWidth } from './lib'

// ---------- provenance (R19): every panel says where its content comes from ----------
export type Kind = 'facts' | 'prediction' | 'generated' | 'rule'

const PROV: Record<Kind, { label: string; title: string }> = {
  facts: { label: 'Ledger fact', title: 'Read from the transaction ledger or system logs' },
  prediction: { label: 'Model estimate', title: 'A machine-learning estimate. It can be wrong.' },
  generated: { label: 'Drafted text', title: 'Written from a template or by the language model, then checked by code' },
  rule: { label: 'Policy rule', title: 'A written business rule that cites the procedure it follows' },
}

// Distinct shapes, so the layer reads without colour.
export function ProvGlyph({ kind, light = false }: { kind: Kind; light?: boolean }) {
  const ink = light ? '#f4f7f5' : '#0f2a24'
  if (kind === 'facts') return <svg width="10" height="10" aria-hidden="true"><rect width="10" height="10" rx="2" fill={light ? '#9fe0c3' : '#006a4e'} /></svg>
  if (kind === 'prediction') return <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="none" stroke={light ? '#e3a008' : '#a77300'} strokeWidth="1.6" strokeDasharray="2.2 1.7" /></svg>
  if (kind === 'generated') return <svg width="10" height="10" aria-hidden="true"><path d="M1.5 8.5 8.5 1.5M1.5 8.5h3" stroke={light ? '#a9bdb6' : '#3e554e'} strokeWidth="1.8" strokeLinecap="round" /></svg>
  return <svg width="10" height="10" aria-hidden="true"><path d="M5 .8 9.2 5 5 9.2.8 5Z" fill={ink} /></svg>
}

export function Provenance({ kind, light = false }: { kind: Kind; light?: boolean }) {
  return (
    <span title={PROV[kind].title} className={`inline-flex items-center gap-1.5 text-[12.5px] whitespace-nowrap ${light ? 'text-mist' : 'text-ink-3'}`}>
      <ProvGlyph kind={kind} light={light} />
      {PROV[kind].label}
    </span>
  )
}

export function Panel({ title, kind, aside, children, className = '', id }: {
  title: ReactNode; kind?: Kind; aside?: ReactNode; children: ReactNode; className?: string; id?: string
}) {
  return (
    <section id={id} className={`bg-surface border border-line rounded-xl ${className}`}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-4">
        <h3 className="text-[17px] font-semibold">{title}</h3>
        <div className="ml-auto flex items-center gap-3">{aside}{kind && <Provenance kind={kind} />}</div>
      </header>
      <div className="px-5 pb-5 pt-3">{children}</div>
    </section>
  )
}

// ---------- small marks ----------
export function TypeMark({ type, label, confidence }: { type: string | null; label?: string; confidence?: number | null }) {
  const tone = (type && TYPE_TONE[type]) || '#a9bdb6'
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: tone }} aria-hidden="true" />
      <span className="font-medium">{label ?? (type ? TYPE_LABEL[type] : 'Needs information')}</span>
      {confidence !== null && confidence !== undefined && <span className="num text-ink-3">{Math.round(confidence * 100)}%</span>}
    </span>
  )
}

export function SlaText({ sla }: { sla: Sla }) {
  const tone = sla.breached ? 'text-signal font-semibold' : sla.working_days_left <= 3 ? 'text-turmeric-ink font-medium' : 'text-ink-2'
  return (
    <span className={`whitespace-nowrap ${tone}`} title={`Resolve by ${sla.deadline}. Bangladesh MFS Regulations 2022 §17.3: 10 working days, Sunday to Thursday.`}>
      {sla.breached ? 'Deadline passed' : `${sla.working_days_left} working ${sla.working_days_left === 1 ? 'day' : 'days'} left`}
    </span>
  )
}

export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-ink-3">{label}</div>
      <div className="num text-[26px] leading-tight font-semibold" style={tone ? { color: tone } : undefined}>{value}</div>
      {note && <div className="text-[12.5px] text-ink-3">{note}</div>}
    </div>
  )
}

// ---------- model output ----------
export function ProbBars({ probs }: { probs: Record<string, number> }) {
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-2">
      {rows.map(([k, v], i) => (
        <div key={k} className="grid grid-cols-[minmax(0,10rem)_1fr_3rem] items-center gap-3 text-[14px]">
          <span className={i === 0 ? 'font-medium' : 'text-ink-2'}>{TYPE_LABEL[k] ?? k}</span>
          <div className="h-2 bg-paper-2 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.max(v * 100, 1.5)}%`, background: i === 0 ? TYPE_TONE[k] : '#c4d0cb' }} />
          </div>
          <span className="num text-right text-ink-2">{Math.round(v * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

// TreeSHAP contributions: how far each fact pushed the model toward the predicted type.
export function ContribBars({ reasons, tone }: { reasons: Reason[]; tone: string }) {
  const max = Math.max(...reasons.map((r) => r.weight), 0.001)
  return (
    <ol className="space-y-3.5">
      {reasons.map((r) => (
        <li key={r.feature}>
          <p className="text-[14.5px] leading-snug">{r.text ?? r.label}</p>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-1.5 rounded-full" style={{ width: `${Math.max((r.weight / max) * 72, 3)}%`, background: tone }} />
            <span className="num text-[12px] text-ink-3">+{r.weight.toFixed(2)}</span>
          </div>
        </li>
      ))}
    </ol>
  )
}

// ---------- the taka drain: where the disputed money is, from the transfer to "if no one acts" ----------
const HORIZON: Record<number, string> = { 0: 'now', 60: '+1 h', 360: '+6 h', 1440: '+1 day', 2880: '+2 days', 4320: '+3 days' }
const MINT = '#9fe0c3'
const ROSE = '#ff9aa8'

function hopLabel(s: TrailStep) {
  const who = s.to_kind === 'agent' ? 'agent' : s.to_kind === 'merchant' ? 'merchant' : 'wallet'
  const what = s.type === 'cash_out' ? 'Cash-out at' : s.type === 'payment' ? 'Payment to' : 'Sent on to'
  return `${what} ${who} ${mask(s.to)}`
}

export function TakaDrain({ amount, past, curve, trail, transferTs, complaintTs, lostByWaiting, waitHours }: {
  amount: number; past: DrainPoint[]; curve: CurvePoint[]; trail: TrailStep[]; transferTs: string; complaintTs: string
  lostByWaiting: number; waitHours: number
}) {
  const [ref, W] = useWidth(880)
  const narrow = W < 560
  const H = narrow ? 220 : 250
  const L = narrow ? 6 : 58, R = narrow ? 10 : 22, T = 34, B = 44
  const plotW = Math.max(W - L - R, 100)
  const pastW = plotW * (narrow ? 0.34 : 0.38)
  const futW = plotW - pastW
  const delay = Math.max(past.length ? past[past.length - 1].minutes : 0, 1)
  const top = Math.max(amount, 1)
  const xp = (m: number) => L + (Math.min(m, delay) / delay) * pastW
  const xf = (i: number) => L + pastW + (i / Math.max(curve.length - 1, 1)) * futW
  const y = (v: number) => T + (1 - Math.min(v, top) / top) * (H - T - B)
  const base = H - B
  const xNow = L + pastW
  const now = curve[0]?.expected ?? past[past.length - 1]?.holdable ?? 0
  const last = curve[curve.length - 1]

  let line = ''
  past.forEach((p, i) => { line += i === 0 ? `M${xp(p.minutes)},${y(p.holdable)}` : ` H${xp(p.minutes)} V${y(p.holdable)}` })
  if (!past.length) line = `M${xp(0)},${y(now)}`
  line += ` H${xNow}`
  const fut = curve.map((c, i) => `${i ? 'L' : 'M'}${xf(i)},${y(c.expected)}`).join(' ')

  const t0 = new Date(transferTs).getTime()
  const outs = trail.filter((s) => s.hop >= 1).map((s) => ({ ...s, at: (new Date(s.ts).getTime() - t0) / 60000 }))
  const labelled = [...outs].sort((a, b) => b.amount - a.amount).slice(0, narrow ? 1 : 3)
  const holdAt = (m: number) => {
    let v = amount
    for (const p of past) if (p.minutes <= m) v = p.holdable
    return v
  }

  return (
    <section className="bg-night text-paper rounded-2xl px-5 pt-5 pb-4 md:px-7 md:pt-6" aria-label="Where the disputed money is">
      <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
        <div className="max-w-md">
          <h2 className="text-[22px] font-semibold">Where the {taka(amount)} is now</h2>
          <p className="text-[13.5px] text-mist mt-1">Money still in the receiving wallet can be held. Once it is cashed out at an agent, it is very hard to get back.</p>
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-2 md:ml-auto">
          <div>
            <dt className="text-[12.5px] text-mist">Still holdable</dt>
            <dd className="num text-[34px] leading-none font-semibold mt-1" style={{ color: MINT }}>{taka(now)}</dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-mist">No longer holdable</dt>
            <dd className="num text-[34px] leading-none font-semibold mt-1" style={{ color: ROSE }}>{taka(Math.max(amount - now, 0))}</dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-mist">At risk if it waits {waitHours} h</dt>
            <dd className="num text-[34px] leading-none font-semibold mt-1 text-turmeric">{taka(lostByWaiting)}</dd>
          </div>
        </dl>
      </div>

      <div ref={ref} className="mt-5 -mx-1">
        <svg width={W} height={H} role="img" aria-label={`Holdable money fell from ${taka(amount)} to ${taka(now)} before the complaint; the model expects ${taka(last?.expected)} by three days if no one acts.`}>
          <defs>
            <pattern id="hatch-rose" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill={ROSE} fillOpacity="0.08" />
              <line x1="0" y1="0" x2="0" y2="6" stroke={ROSE} strokeOpacity="0.45" strokeWidth="1.4" />
            </pattern>
            <pattern id="hatch-mint" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill={MINT} fillOpacity="0.1" />
              <line x1="0" y1="0" x2="0" y2="6" stroke={MINT} strokeOpacity="0.4" strokeWidth="1.4" />
            </pattern>
          </defs>
          {/* region captions */}
          <text x={L} y={14} fontSize="12" fill="#a9bdb6">{narrow ? 'Before' : 'Before the complaint'}</text>
          <text x={xNow + 10} y={14} fontSize="12" fill="#a9bdb6">{narrow ? 'If no one acts' : 'If no one acts (estimate)'}</text>
          {/* money gone and money still there, ledger facts */}
          <path d={`${line} V${y(top)} H${xp(0)} Z`} fill={ROSE} fillOpacity="0.28" />
          <path d={`${line} V${base} H${xp(0)} Z`} fill={MINT} fillOpacity="0.3" />
          {/* the estimate, hatched */}
          {curve.length > 1 && <path d={`${fut} L${xf(curve.length - 1)},${y(top)} L${xf(0)},${y(top)} Z`} fill="url(#hatch-rose)" />}
          {curve.length > 1 && <path d={`${fut} V${base} H${xf(0)} Z`} fill="url(#hatch-mint)" />}
          {/* disputed amount and baseline */}
          <line x1={L} x2={L + plotW} y1={y(top)} y2={y(top)} stroke="#a9bdb6" strokeDasharray="3 4" strokeWidth="1" />
          <line x1={L} x2={L + plotW} y1={base} y2={base} stroke="#2f5249" />
          {!narrow && <text x={L - 8} y={y(top) + 4} fontSize="12" textAnchor="end" fill="#a9bdb6" className="num">{taka(top)}</text>}
          {!narrow && <text x={L - 8} y={base + 4} fontSize="12" textAnchor="end" fill="#a9bdb6" className="num">৳0</text>}
          <path d={line} fill="none" stroke={MINT} strokeWidth="2.2" />
          {curve.length > 1 && <path d={fut} fill="none" stroke="#e3a008" strokeWidth="2" strokeDasharray="6 5" />}
          {/* outflows */}
          {outs.map((s) => (
            <circle key={s.trx_id} cx={xp(s.at)} cy={y(holdAt(s.at))} r="3.5" fill={ROSE} stroke="#0f2a24" strokeWidth="1.5" />
          ))}
          {labelled.map((s) => {
            const x = xp(s.at)
            const anchor = x - L < 60 ? 'start' : x > xNow - 50 ? 'end' : 'middle'
            return (
              <text key={`l${s.trx_id}`} x={x} y={Math.min(y(holdAt(s.at)) + 20, base - 6)} fontSize="12" textAnchor={anchor} fill={ROSE} className="num">
                −{taka(s.amount)}
              </text>
            )
          })}
          {/* now */}
          <line x1={xNow} x2={xNow} y1={22} y2={base} stroke="#f4f7f5" strokeWidth="1.5" />
          <circle cx={xNow} cy={y(now)} r="5" fill="#f4f7f5" />
          {last && curve.length > 1 && (
            <>
              <circle cx={xf(curve.length - 1)} cy={y(last.expected)} r="3.5" fill="#e3a008" />
              <text x={xf(curve.length - 1)} y={y(last.expected) - 10} fontSize="12.5" textAnchor="end" fill="#e3a008" className="num">{taka(last.expected)}</text>
            </>
          )}
          {/* time axis */}
          <text x={xp(0)} y={base + 18} fontSize="12" fill="#a9bdb6">Sent {clock(transferTs)}</text>
          <text x={xNow} y={base + 18} fontSize="12" textAnchor="middle" fill="#f4f7f5" fontWeight="600">Complaint {clock(complaintTs)}</text>
          <text x={xNow} y={base + 34} fontSize="11.5" textAnchor="middle" fill="#a9bdb6">{delay < 60 ? `${Math.round(delay)} min later` : `${Math.floor(delay / 60)} h ${Math.round(delay % 60)} min later`}</text>
          {curve.map((c, i) => i > 0 && (!narrow || i === 3 || i === curve.length - 1) && (
            <g key={c.minutes}>
              <line x1={xf(i)} x2={xf(i)} y1={base} y2={base + 5} stroke="#2f5249" />
              <text x={xf(i)} y={base + 18} fontSize="12" textAnchor={i === curve.length - 1 ? 'end' : 'middle'} fill="#a9bdb6">{HORIZON[c.minutes] ?? `+${c.minutes} min`}</text>
            </g>
          ))}
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12.5px] text-mist border-t border-night-line pt-3">
        <span className="inline-flex items-center gap-2"><span className="w-3 h-3 rounded-sm" style={{ background: MINT, opacity: 0.6 }} />Still in the wallet</span>
        <span className="inline-flex items-center gap-2"><span className="w-3 h-3 rounded-sm" style={{ background: ROSE, opacity: 0.55 }} />Moved out</span>
        <span className="inline-flex items-center gap-2"><Provenance kind="facts" light /> up to the complaint</span>
        <span className="inline-flex items-center gap-2"><Provenance kind="prediction" light /> after it (recoverability model, M5)</span>
      </div>
      {outs.length > 0 && (
        <ul className="mt-3 grid sm:grid-cols-2 gap-x-8 gap-y-1 text-[13.5px]">
          {outs.slice(0, 6).map((s) => (
            <li key={s.trx_id} className="flex items-baseline gap-3">
              <span className="num text-mist w-11 shrink-0">{clock(s.ts)}</span>
              <span className="truncate">{hopLabel(s)}</span>
              <span className="num ml-auto" style={{ color: ROSE }}>−{taka(s.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ---------- intended number ----------
export function NumberDiff({ intended, actual, positions, revealed, labels = ['Usually pays', 'Sent to'], small = false }: {
  intended: string; actual: string; positions: number[]; revealed: boolean; labels?: [string, string]; small?: boolean
}) {
  const row = (num: string, label: string, sent: boolean) => (
    <div className={small ? 'space-y-1' : 'flex items-center gap-3'}>
      <span className={`${small ? 'block' : 'w-24 shrink-0'} text-[13px] text-ink-3`}>{label}</span>
      <span className="flex gap-[3px]" aria-label={`${label} ${revealed ? num : mask(num)}`}>
        {num.split('').map((d, i) => {
          const diff = positions.includes(i)
          const hidden = !revealed && i >= 3 && i < 7 && !diff
          return (
            <span key={i} className={`num ${small ? 'w-[19px] h-7 text-[15px]' : 'w-[22px] h-8 text-[17px]'} grid place-items-center rounded-md ${diff ? (sent ? 'bg-signal text-white font-semibold' : 'bg-flag text-white font-semibold') : 'bg-paper-2 text-ink'}`}>
              {hidden ? '•' : d}
            </span>
          )
        })}
      </span>
    </div>
  )
  return (
    <div className="space-y-2 overflow-x-auto">
      {row(intended, labels[0], false)}
      {row(actual, labels[1], true)}
    </div>
  )
}

// ---------- the ring around the receiving wallet ----------
const NODE_STYLE: Record<string, { fill: string; stroke: string }> = {
  center: { fill: '#0f2a24', stroke: '#0f2a24' },
  this_customer: { fill: '#e3a008', stroke: '#7a5200' },
  complainant: { fill: '#fbe4e7', stroke: '#d7263d' },
  agent: { fill: '#d7263d', stroke: '#b01c30' },
  merchant: { fill: '#e8eeeb', stroke: '#6b7f78' },
  mno: { fill: '#e8eeeb', stroke: '#6b7f78' },
  wallet: { fill: '#ffffff', stroke: '#3e554e' },
}
const KIND_NAME: Record<string, string> = { agent: 'Agent', merchant: 'Merchant', mno: 'Operator', wallet: 'Wallet' }

export function RingGraph({ network, revealed }: { network: Network; revealed: boolean }) {
  const [ref, W] = useWidth(720)
  const left = network.nodes.filter((n) => n.kind === 'complainant' || n.kind === 'this_customer')
  const right = network.nodes.filter((n) => !['center', 'complainant', 'this_customer'].includes(n.kind))
  const rows = Math.max(left.length, right.length, 1)
  const narrow = W < 540
  const H = Math.max(220, Math.min(rows * 30 + 70, 520))
  const cy = H / 2
  const spread = H - 70
  const name = (id: string) => (revealed ? id : mask(id))
  const amountTo = (id: string) => network.edges.find((e) => e.target === id && e.source === network.center)?.amount
  const leftLabel = (kind: string, id: string) => (kind === 'this_customer' ? (narrow ? 'This customer' : `This customer ${name(id)}`) : name(id))
  const showLeft = (kind: string) => !narrow || kind === 'this_customer'
  const rightLabel = (kind: string, id: string) => (narrow ? taka(amountTo(id)) : `${KIND_NAME[kind] ?? 'Wallet'} ${name(id)}, ${taka(amountTo(id))}`)
  // leave room for the longest label on each side, so nothing is clipped
  const CH = 6.9
  const leftW = Math.max(0, ...left.filter((n) => showLeft(n.kind)).map((n) => leftLabel(n.kind, n.id).length * CH)) + 24
  const rightW = Math.max(0, ...right.map((n) => rightLabel(n.kind, n.id).length * CH)) + 24
  const xL = Math.min(leftW, W * 0.42), xR = Math.max(W - rightW, W * 0.58)
  const cx = (xL + xR) / 2
  const place = (i: number, n: number, side: -1 | 1) => {
    const t = n === 1 ? 0 : i / (n - 1) - 0.5
    const edge = side === -1 ? xL : xR
    return { x: edge + side * -1 * Math.abs(t) * Math.abs(cx - edge) * 0.3, y: cy + t * spread }
  }
  const pos = new Map<string, { x: number; y: number }>()
  pos.set(network.center ?? '', { x: cx, y: cy })
  left.forEach((n, i) => pos.set(n.id, place(i, left.length, -1)))
  right.forEach((n, i) => pos.set(n.id, place(i, right.length, 1)))
  const maxAmt = Math.max(...network.edges.map((e) => e.amount), 1)
  const kind = new Map(network.nodes.map((n) => [n.id, n.kind]))

  return (
    <div ref={ref}>
      <svg width={W} height={H} role="img" aria-label={`${network.complainants} other customers sent money to this wallet and complained; it passed money on to ${right.length} accounts.`}>
        {network.edges.map((e, i) => {
          const a = pos.get(e.source), b = pos.get(e.target)
          if (!a || !b) return null
          const mx = (a.x + b.x) / 2
          const k = kind.get(e.source) === 'center' ? kind.get(e.target) : kind.get(e.source)
          const stroke = k === 'this_customer' ? '#e3a008' : k === 'complainant' ? '#e9a3ad' : k === 'agent' ? '#d7263d' : '#9fb1aa'
          return (
            <path key={i} d={`M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`} fill="none" stroke={stroke}
              strokeWidth={1 + 4 * Math.sqrt(e.amount / maxAmt)} strokeOpacity={k === 'complainant' ? 0.8 : 1}>
              <title>{`${taka(e.amount)} ${e.kind.replace('_', ' ')}`}</title>
            </path>
          )
        })}
        {network.nodes.map((n) => {
          const p = pos.get(n.id)
          if (!p) return null
          const s = NODE_STYLE[n.kind] ?? NODE_STYLE.wallet
          const isLeft = n.kind === 'complainant' || n.kind === 'this_customer'
          if (n.kind === 'center') {
            return (
              <g key={n.id}>
                <circle cx={p.x} cy={p.y} r="17" fill={s.fill} />
                <circle cx={p.x} cy={p.y} r="23" fill="none" stroke="#0f2a24" strokeOpacity="0.18" strokeWidth="5" />
                <text x={p.x} y={p.y + 42} textAnchor="middle" fontSize="13" fontWeight="600" fill="#0f2a24">Receiving wallet</text>
                <text x={p.x} y={p.y + 58} textAnchor="middle" fontSize="12.5" fill="#3e554e" className="num">{name(n.id)}</text>
              </g>
            )
          }
          const square = n.kind === 'agent' || n.kind === 'merchant' || n.kind === 'mno'
          const r = n.kind === 'this_customer' ? 8 : 6
          return (
            <g key={n.id}>
              {square
                ? <rect x={p.x - 6.5} y={p.y - 6.5} width="13" height="13" rx="3" fill={s.fill} stroke={s.stroke} strokeWidth="1.5" />
                : <circle cx={p.x} cy={p.y} r={r} fill={s.fill} stroke={s.stroke} strokeWidth="1.5" />}
              {isLeft && showLeft(n.kind) && (
                <text x={p.x - 13} y={p.y + 4} textAnchor="end" fontSize="12.5" fill={n.kind === 'this_customer' ? '#7a5200' : '#3e554e'} fontWeight={n.kind === 'this_customer' ? 600 : 400} className="num">
                  {leftLabel(n.kind, n.id)}
                </text>
              )}
              {!isLeft && (
                <text x={p.x + 13} y={p.y + 4} fontSize="12.5" fill="#3e554e" className="num">
                  {rightLabel(n.kind, n.id)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ---------- audit ----------
const ACTION: Record<string, string> = {
  'case.created': 'Case opened', 'case.approve': 'Recommendation approved', 'case.edit': 'Approved with edited drafts',
  'case.override': 'Recommendation overridden', 'case.contested': 'Customer asked for a human review',
  'case.exported': 'Evidence exported', 'pii.reveal': 'Numbers revealed',
}

export function AuditList({ entries }: { entries: AuditEntry[] }) {
  return (
    <ol className="relative border-l border-line ml-1.5 space-y-3">
      {entries.map((e) => (
        <li key={e.seq} className="pl-4 relative">
          <span className="absolute -left-[5px] top-2 w-2.5 h-2.5 rounded-full bg-surface border-2 border-ink-3" aria-hidden="true" />
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium text-[14px]">{ACTION[e.action] ?? e.action}</span>
            <span className="text-[13px] text-ink-3">by {e.actor} ({e.role}), {clock(e.ts)}</span>
          </div>
          <div className="font-mono text-[11.5px] text-ink-3 truncate" title={e.hash}>hash {e.hash.slice(0, 16)}</div>
        </li>
      ))}
    </ol>
  )
}

// ---------- controls ----------
export function Button({ children, tone = 'primary', size = 'md', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: 'primary' | 'secondary' | 'danger' | 'quiet' | 'warn' | 'light' | 'outline-light'; size?: 'sm' | 'md' | 'lg'
}) {
  const style = {
    primary: 'bg-flag hover:bg-flag-2 text-white',
    secondary: 'bg-surface hover:bg-paper text-ink border border-line',
    danger: 'bg-surface hover:bg-signal-soft text-signal-2 border border-signal/40',
    warn: 'bg-signal hover:bg-signal-2 text-white',
    quiet: 'text-ink-2 hover:text-ink hover:bg-paper-2',
    light: 'bg-paper hover:bg-white text-ink',
    'outline-light': 'text-paper border border-night-line hover:bg-night-2',
  }[tone]
  const pad = { sm: 'text-[13.5px] px-3 py-1.5', md: 'text-[14.5px] px-4 py-2', lg: 'text-[16px] px-5 py-3' }[size]
  return (
    <button {...props} className={`inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors disabled:opacity-45 disabled:cursor-not-allowed ${pad} ${style} ${props.className ?? ''}`}>
      {children}
    </button>
  )
}

export function Notice({ tone = 'turmeric', children }: { tone?: 'turmeric' | 'signal' | 'flag'; children: ReactNode }) {
  const style = { turmeric: 'bg-turmeric-soft text-turmeric-ink', signal: 'bg-signal-soft text-signal-2', flag: 'bg-flag-soft text-flag-2' }[tone]
  return <div className={`rounded-lg px-4 py-3 text-[14px] ${style}`}>{children}</div>
}
