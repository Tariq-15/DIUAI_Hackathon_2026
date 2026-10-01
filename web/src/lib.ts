import { useEffect, useState } from 'react'

export const taka = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `৳${Math.round(n).toLocaleString('en-US')}`

// R9: numbers are masked to the last 4 digits unless an agent reveals them (and the reveal is logged).
export const mask = (n: string | null | undefined) => (n ? `•••••••${n.slice(-4)}` : '—')

export const when = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export const pct = (p: number | null | undefined) => (p === null || p === undefined ? '—' : `${Math.round(p * 100)}%`)

export const TYPE_STYLE: Record<string, string> = {
  genuine_wrong_send: 'bg-sky-100 text-sky-800 ring-sky-200',
  scam_victim: 'bg-rose-100 text-rose-800 ring-rose-200',
  double_recovery: 'bg-amber-100 text-amber-800 ring-amber-200',
  false_claim: 'bg-violet-100 text-violet-800 ring-violet-200',
  technical_failure: 'bg-slate-200 text-slate-800 ring-slate-300',
}

export const TYPE_LABEL: Record<string, string> = {
  genuine_wrong_send: 'Genuine wrong-send',
  scam_victim: 'Scam victim',
  double_recovery: 'Double-recovery claim',
  false_claim: 'False claim',
  technical_failure: 'Technical failure',
}

export function useHashRoute(): [string, (to: string) => void] {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/')
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash.slice(1) || '/')
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return [route, (to: string) => (window.location.hash = to)]
}
