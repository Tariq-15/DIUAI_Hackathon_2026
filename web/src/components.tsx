import { Background, type Edge, MarkerType, type Node, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { AuditEntry, CurvePoint, Sla, TrailStep } from './api'
import { mask, taka, TYPE_LABEL, TYPE_STYLE, when } from './lib'

export function PrototypeBanner() {
  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-4 py-1.5 text-center">
      Hackathon prototype · synthetic data only · not an official upay product or message
    </div>
  )
}

// R19: every panel says whether it shows facts from the ledger, a model prediction, or generated text.
const LAYER = {
  facts: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  prediction: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  generated: 'bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-200',
  rule: 'bg-slate-100 text-slate-700 ring-slate-200',
} as const

export function LayerTag({ kind }: { kind: keyof typeof LAYER }) {
  const label = { facts: 'Facts', prediction: 'Prediction', generated: 'Generated', rule: 'Rule' }[kind]
  return <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ring-1 ${LAYER[kind]}`}>{label}</span>
}

export function Card({ title, tag, children, right }: { title: string; tag?: keyof typeof LAYER; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="bg-white rounded-xl ring-1 ring-slate-200 shadow-sm">
      <header className="flex items-center gap-2 px-4 pt-3 pb-2 border-b border-slate-100">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {tag && <LayerTag kind={tag} />}
        <div className="ml-auto">{right}</div>
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

export function TypeBadge({ type, label }: { type: string | null; label?: string }) {
  const style = (type && TYPE_STYLE[type]) || 'bg-slate-100 text-slate-700 ring-slate-200'
  return <span className={`text-xs font-medium px-2 py-0.5 rounded-full ring-1 ${style}`}>{label ?? (type ? TYPE_LABEL[type] : 'Needs information')}</span>
}

export function SlaChip({ sla }: { sla: Sla }) {
  const tone = sla.breached ? 'bg-rose-600 text-white' : sla.working_days_left <= 3 ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${tone}`} title="Bangladesh MFS Regulations 2022 §17.3: resolve within 10 working days">
      {sla.breached ? 'SLA breached' : `${sla.working_days_left} working days left`} · {sla.deadline}
    </span>
  )
}

export function ProbBars({ probs }: { probs: Record<string, number> }) {
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-1.5">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-xs">
          <span className="w-40 text-slate-600">{TYPE_LABEL[k] ?? k}</span>
          <div className="flex-1 h-2 bg-slate-100 rounded">
            <div className={`h-2 rounded ${v === rows[0][1] ? 'bg-indigo-600' : 'bg-slate-300'}`} style={{ width: `${Math.max(v * 100, 1)}%` }} />
          </div>
          <span className="w-10 text-right tabular-nums text-slate-700">{Math.round(v * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

const CURVE_LABELS: Record<number, string> = { 0: 'now', 60: '1 h', 360: '6 h', 1440: '24 h', 2880: '48 h', 4320: '72 h' }

export function RecoveryChart({ curve, amount }: { curve: CurvePoint[]; amount: number }) {
  if (!curve.length) return <p className="text-sm text-slate-500">No transfer matched yet.</p>
  const W = 420, H = 150, L = 46, B = 24, T = 12
  const max = Math.max(amount, ...curve.map((p) => p.expected), 1)
  const x = (i: number) => L + (i * (W - L - 12)) / Math.max(curve.length - 1, 1)
  const y = (v: number) => T + (1 - v / max) * (H - T - B)
  const path = curve.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.expected)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Expected holdable taka over time">
      <line x1={L} x2={W - 12} y1={y(amount)} y2={y(amount)} stroke="#cbd5e1" strokeDasharray="4 4" />
      <text x={W - 12} y={y(amount) - 4} textAnchor="end" fontSize="10" fill="#64748b">disputed {taka(amount)}</text>
      <line x1={L} x2={W - 12} y1={H - B} y2={H - B} stroke="#94a3b8" />
      <path d={`${path} L${x(curve.length - 1)},${H - B} L${x(0)},${H - B} Z`} fill="#4f46e5" fillOpacity="0.08" />
      <path d={path} fill="none" stroke="#4f46e5" strokeWidth="2" />
      {curve.map((p, i) => (
        <g key={p.minutes}>
          <circle cx={x(i)} cy={y(p.expected)} r="3.5" fill="#4f46e5">
            <title>{`${CURVE_LABELS[p.minutes] ?? p.minutes + ' min'}: ${taka(p.expected)} (hold chance ${Math.round(p.p_hold * 100)}%)`}</title>
          </circle>
          <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="#64748b">{CURVE_LABELS[p.minutes] ?? p.minutes}</text>
          {(i === 0 || i === curve.length - 1) && (
            <text x={x(i)} y={y(p.expected) - 8} textAnchor={i === 0 ? 'start' : 'end'} fontSize="11" fontWeight="600" fill="#1e1b4b">{taka(p.expected)}</text>
          )}
        </g>
      ))}
    </svg>
  )
}

export function NumberDiff({ intended, actual, positions, revealed }: { intended: string; actual: string; positions: number[]; revealed: boolean }) {
  const show = (num: string) =>
    num.split('').map((d, i) => {
      const hidden = !revealed && i < 7 && !positions.includes(i)
      return (
        <span key={i} className={`inline-block w-4 text-center font-mono ${positions.includes(i) ? 'bg-amber-200 text-amber-950 rounded font-bold' : ''}`}>
          {hidden ? '•' : d}
        </span>
      )
    })
  return (
    <div className="text-sm space-y-1">
      <div className="flex items-center gap-2"><span className="w-20 text-xs text-slate-500">Paid before</span>{show(intended)}</div>
      <div className="flex items-center gap-2"><span className="w-20 text-xs text-slate-500">Sent to</span>{show(actual)}</div>
    </div>
  )
}

export function MoneyTrail({ trail, revealed }: { trail: TrailStep[]; revealed: boolean }) {
  if (!trail.length) return <p className="text-sm text-slate-500">No money trail.</p>
  const label = (n: string, kind?: string) => (kind === 'agent' ? `Agent ${mask(n)}` : kind === 'merchant' ? `Merchant ${mask(n)}` : revealed ? n : mask(n))
  const nodes: Node[] = []
  const edges: Edge[] = []
  const seen = new Map<string, { x: number; y: number }>()
  // top to bottom: complainant, then the receiving wallet, then where the money went next
  const place = (id: string, hop: number, text: string, tone: string) => {
    if (seen.has(id)) return
    const count = [...seen.values()].filter((p) => p.y === hop * 110).length
    const pos = { x: count * 200, y: hop * 110 }
    seen.set(id, pos)
    nodes.push({ id, position: pos, data: { label: text }, style: { fontSize: 12, padding: 8, borderRadius: 8, width: 170, background: tone, border: '1px solid #cbd5e1' } })
  }
  const first = trail[0]
  place(first.from, 0, `Complainant ${label(first.from)}`, '#f0fdfa')
  trail.forEach((s, i) => {
    place(s.to, s.hop + 1, `${label(s.to, s.to_kind)}${s.type === 'cash_out' ? ' (cash-out)' : ''}`, s.hop === 0 ? '#eef2ff' : s.to_kind === 'agent' ? '#fff1f2' : '#ffffff')
    const t = new Date(s.ts)
    edges.push({
      id: `e${i}`, source: s.from, target: s.to,
      label: `${taka(s.amount)} · ${Number.isNaN(t.getTime()) ? when(s.ts) : t.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`,
      labelStyle: { fontSize: 11, fontWeight: 600 }, labelBgPadding: [4, 2], markerEnd: { type: MarkerType.ArrowClosed }, animated: s.hop === 0,
      style: { stroke: s.hop === 0 ? '#4f46e5' : '#94a3b8', strokeWidth: 1.5 },
    })
  })
  return (
    <div className="h-72 rounded-lg ring-1 ring-slate-100">
      <ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.15, maxZoom: 1.1 }} proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false}>
        <Background gap={16} color="#f1f5f9" />
      </ReactFlow>
    </div>
  )
}

export function AuditList({ entries }: { entries: AuditEntry[] }) {
  return (
    <ol className="space-y-1.5 text-xs">
      {entries.map((e) => (
        <li key={e.seq} className="flex gap-2">
          <span className="text-slate-400 tabular-nums">#{e.seq}</span>
          <span className="font-medium">{e.action}</span>
          <span className="text-slate-600">by {e.actor} ({e.role})</span>
          <span className="ml-auto font-mono text-slate-400" title={e.hash}>{e.hash.slice(0, 10)}…</span>
        </li>
      ))}
    </ol>
  )
}

export function Button({ children, tone = 'primary', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'secondary' | 'danger' }) {
  const style = {
    primary: 'bg-teal-700 hover:bg-teal-800 text-white',
    secondary: 'bg-white hover:bg-slate-50 text-slate-800 ring-1 ring-slate-300',
    danger: 'bg-white hover:bg-rose-50 text-rose-700 ring-1 ring-rose-300',
  }[tone]
  return (
    <button {...props} className={`text-sm font-medium px-3 py-1.5 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${style} ${props.className ?? ''}`}>
      {children}
    </button>
  )
}
