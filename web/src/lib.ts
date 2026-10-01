import { useEffect, useState } from 'react'

export const taka = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `৳${Math.round(n).toLocaleString('en-US')}`

// R9: numbers are masked to the last 4 digits unless an agent reveals them (and the reveal is logged).
export const mask = (n: string | null | undefined) => (n ? `•••• ${n.slice(-4)}` : '—')

const valid = (iso: string) => !Number.isNaN(new Date(iso).getTime())

export const when = (iso: string) =>
  valid(iso) ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : iso

export const clock = (iso: string) =>
  valid(iso) ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : iso

export const day = (iso: string) =>
  valid(iso) ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : iso

export const pct = (p: number | null | undefined, digits = 0) =>
  p === null || p === undefined ? '—' : `${(p * 100).toFixed(digits)}%`

export const span = (minutes: number) => {
  const m = Math.round(minutes)
  if (m < 60) return `${m} min`
  if (m < 48 * 60) return `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ''}`
  return `${Math.round(m / 1440)} days`
}

const BN_DIGITS = '০১২৩৪৫৬৭৮৯'
export const bnNum = (s: string | number) => String(s).replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)])

export const TYPE_LABEL: Record<string, string> = {
  genuine_wrong_send: 'Genuine wrong-send',
  scam_victim: 'Scam victim',
  double_recovery: 'Double-recovery claim',
  false_claim: 'False claim',
  technical_failure: 'Technical failure',
}

// One colour per case type, drawn from the palette: green can come back, red is a scam, turmeric needs care.
export const TYPE_TONE: Record<string, string> = {
  genuine_wrong_send: '#006a4e',
  scam_victim: '#d7263d',
  double_recovery: '#e3a008',
  false_claim: '#3e554e',
  technical_failure: '#6b7f78',
}

export function useHashRoute(): [string, (to: string) => void] {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/')
  useEffect(() => {
    const onChange = () => {
      setRoute(window.location.hash.slice(1) || '/')
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return [route, (to: string) => (window.location.hash = to)]
}

// Width of an element, so charts draw at real pixel size and text never stretches.
// A callback ref, so it also works for elements that appear after data loads.
export function useWidth(fallback = 640): [(el: HTMLElement | null) => void, number] {
  const [el, setEl] = useState<HTMLElement | null>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width) || fallback))
    ro.observe(el)
    return () => ro.disconnect()
  }, [el, fallback])
  return [setEl, width]
}
