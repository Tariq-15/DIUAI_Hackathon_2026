const STEPS = [
  ['Read', 'Bangla, Banglish or English complaint → amount, number, time, TrxID (rules first, LLM optional, masked)'],
  ['Match', 'Finds the disputed transfer in the ledger'],
  ['Explain', 'Typo against a frequent contact? Money already moving? Others complained about this wallet?'],
  ['Classify', 'Genuine wrong-send, scam victim, double-recovery claim, false claim or technical failure'],
  ['Prioritise', 'Ranks the queue by taka at risk if the case waits, with a 10-working-day SLA floor'],
  ['Recommend', 'Business rules choose the action; a named human approves; drafts in Bangla and English'],
]

export default function Home({ go }: { go: (to: string) => void }) {
  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <p className="text-sm font-medium text-teal-700">Track 06 · Operations & Service Intelligence</p>
      <h1 className="text-3xl font-bold mt-1">"I sent money to the wrong number."</h1>
      <p className="mt-3 text-lg text-slate-700 max-w-3xl">
        A wrong-send dispute is a race against cash-out. Ferot reads the complaint, rebuilds the money trail, tells a
        typo from a scam or a false claim, and puts the case where the money is about to leave at the top of the queue.
        Humans decide every action.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <button onClick={() => go('/customer')} className="px-4 py-2 rounded-lg bg-teal-700 text-white font-medium">Try the customer app</button>
        <button onClick={() => go('/console')} className="px-4 py-2 rounded-lg bg-white ring-1 ring-slate-300 font-medium">Open the agent console</button>
        <button onClick={() => go('/analyst')} className="px-4 py-2 rounded-lg bg-white ring-1 ring-slate-300 font-medium">See the evidence</button>
      </div>
      <ol className="mt-10 grid md:grid-cols-3 gap-4">
        {STEPS.map(([title, text], i) => (
          <li key={title} className="bg-white rounded-xl ring-1 ring-slate-200 p-4">
            <span className="text-xs font-semibold text-slate-400">{i + 1}</span>
            <h3 className="font-semibold">{title}</h3>
            <p className="text-sm text-slate-600 mt-1">{text}</p>
          </li>
        ))}
      </ol>
      <div className="mt-10 grid md:grid-cols-3 gap-4 text-sm">
        <div className="bg-emerald-50 rounded-xl p-4 ring-1 ring-emerald-200">
          <h3 className="font-semibold text-emerald-900">Built to Bangladesh MFS rules</h3>
          <p className="text-emerald-900/80 mt-1">10-working-day dispute deadline and dispute log (MFS Regulations 2022 §17.3), 6-year records (§18), tamper-evident audit (§12.2), no tipping off (MLPA §6).</p>
        </div>
        <div className="bg-indigo-50 rounded-xl p-4 ring-1 ring-indigo-200">
          <h3 className="font-semibold text-indigo-900">ML decides, humans approve</h3>
          <p className="text-indigo-900/80 mt-1">LightGBM models with per-case reasons. The LLM only reads text in and polishes drafts that code then checks.</p>
        </div>
        <div className="bg-amber-50 rounded-xl p-4 ring-1 ring-amber-200">
          <h3 className="font-semibold text-amber-900">Honest about limits</h3>
          <p className="text-amber-900/80 mt-1">Synthetic data only. Results, baselines, an oracle ceiling and known failure cases are on the evidence page.</p>
        </div>
      </div>
    </div>
  )
}
