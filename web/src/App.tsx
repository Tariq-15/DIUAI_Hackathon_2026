import { useEffect, useState } from 'react'
import { api } from './api'
import { PrototypeBanner } from './components'
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
  { to: '/analyst', label: 'Analyst & evidence' },
]

export default function App() {
  const [route, go] = useHashRoute()
  const [health, setHealth] = useState<{ model_version: string; llm_provider: string } | null>(null)
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  let page = <Home go={go} />
  if (route.startsWith('/customer')) page = <Customer />
  else if (route.startsWith('/console/case/')) page = <CaseView id={route.split('/')[3]} go={go} />
  else if (route.startsWith('/console')) page = <Console go={go} />
  else if (route.startsWith('/analyst')) page = <Analyst />

  return (
    <div className="min-h-screen flex flex-col">
      <PrototypeBanner />
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
          <a href="#/" className="flex items-center gap-2 font-semibold text-slate-900">
            <img src="/favicon.svg" alt="" className="w-7 h-7" />
            Ferot <span className="bn text-slate-500 font-normal">ফেরত</span>
          </a>
          <nav className="flex gap-1 text-sm overflow-x-auto">
            {NAV.map((n) => {
              const active = n.to === '/' ? route === '/' : route.startsWith(n.to)
              return (
                <a key={n.to} href={`#${n.to}`} className={`px-3 py-1.5 rounded-lg whitespace-nowrap ${active ? 'bg-teal-50 text-teal-800 font-medium' : 'text-slate-600 hover:bg-slate-100'}`}>
                  {n.label}
                </a>
              )
            })}
          </nav>
          <span className="ml-auto hidden md:block text-xs text-slate-500">
            {health ? `model ${health.model_version} · LLM: ${health.llm_provider}` : 'API offline'}
          </span>
        </div>
      </header>
      <main className="flex-1">{page}</main>
      <footer className="text-xs text-slate-500 text-center py-4">
        Built for the AI Hackathon 2026 (DIU CPC × upay). Synthetic data; numbers use the 010 prefix. Not affiliated with or endorsed by upay.
      </footer>
    </div>
  )
}
