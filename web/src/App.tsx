import { useEffect, useState } from 'react'
import { api } from './api'
import { useHashRoute } from './lib'
import Analyst from './pages/Analyst'
import CaseView from './pages/CaseView'
import Console from './pages/Console'
import Customer from './pages/Customer'
import Home from './pages/Home'

const NAV = [
  { to: '/', label: 'Overview' },
  { to: '/customer', label: 'Customer app' },
  { to: '/console', label: 'Agent console' },
  { to: '/analyst', label: 'Evidence' },
]

export default function App() {
  const [route, go] = useHashRoute()
  const [health, setHealth] = useState<{ model_version: string; llm_provider: string } | null | undefined>(undefined)
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  let page = <Home go={go} />
  if (route.startsWith('/customer')) page = <Customer go={go} />
  else if (route.startsWith('/console/case/')) page = <CaseView id={route.split('/')[3]} go={go} />
  else if (route.startsWith('/console')) page = <Console go={go} />
  else if (route.startsWith('/analyst')) page = <Analyst go={go} />

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 bg-surface px-3 py-2 rounded">Skip to content</a>
      <header className="bg-night text-paper">
        <div className="max-w-[1240px] mx-auto px-4 md:px-6 flex flex-wrap items-center gap-x-8">
          <a href="#/" className="flex items-baseline gap-2 py-3.5" aria-label="Ferot home">
            <span className="font-display text-[24px] font-semibold leading-none">Ferot</span>
            <span className="font-display text-[19px] leading-none text-turmeric">ফেরত</span>
          </a>
          <nav className="order-3 md:order-none w-full md:w-auto -mx-1 flex overflow-x-auto" aria-label="Main">
            {NAV.map((n) => {
              const active = n.to === '/' ? route === '/' : route.startsWith(n.to)
              return (
                <a key={n.to} href={`#${n.to}`} aria-current={active ? 'page' : undefined}
                  className={`relative px-3 py-3 md:py-5 text-[14.5px] whitespace-nowrap transition-colors ${active ? 'text-paper font-medium' : 'text-mist hover:text-paper'}`}>
                  {n.label}
                  {active && <span className="absolute left-3 right-3 bottom-0 h-[3px] rounded-t bg-turmeric" />}
                </a>
              )
            })}
          </nav>
          <span className="ml-auto hidden lg:flex items-center gap-2 text-[12.5px] text-mist">
            <span className={`w-2 h-2 rounded-full ${health ? 'bg-[#9fe0c3]' : health === null ? 'bg-signal' : 'bg-mist'}`} aria-hidden="true" />
            {health ? `Models ${health.model_version}, language model: ${health.llm_provider}` : health === null ? 'API offline' : 'Connecting'}
          </span>
        </div>
      </header>
      <p className="bg-paper-2 text-ink-2 text-[12.5px] px-4 py-1.5 text-center border-b border-line">
        Hackathon prototype on synthetic data. Not an upay product, and nothing here is an upay message.
      </p>
      <main id="main" className="flex-1">{page}</main>
      <footer className="border-t border-line mt-16">
        <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-6 flex flex-wrap gap-x-8 gap-y-2 text-[13px] text-ink-3">
          <span>Built for AI Hackathon 2026, DIU CPC and upay, Track 06.</span>
          <span>All customers and numbers are synthetic and use the 010 prefix.</span>
          <span>Not affiliated with or endorsed by upay or UCB Fintech.</span>
        </div>
      </footer>
    </div>
  )
}
