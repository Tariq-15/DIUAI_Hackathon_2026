import { type CSSProperties, type ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import { Button, NumberDiff, TypeMark } from '../components'
import { taka } from '../lib'

type Any = Record<string, any>

// The demo complaint, exactly as Rahim typed it (Banglish), and what Ferot reads from it.
function Mark({ children, delay }: { children: ReactNode; delay: number }) {
  return <span className="read-mark rounded-sm px-0.5 -mx-0.5" style={{ animationDelay: `${delay}ms` } as CSSProperties}>{children}</span>
}

const READ = [
  { label: 'Amount', value: '৳5,000', delay: 500 },
  { label: 'What happened', value: 'Wrong number', delay: 900 },
  { label: 'Number', value: '01012 345687', delay: 1300 },
  { label: 'When', value: 'Today, about 14:00', delay: 1700 },
]

const STEPS = [
  ['Read', 'Pulls the amount, number, time and TrxID out of Bangla, Banglish or English. Rules first; the language model only sees masked text.'],
  ['Match', 'Finds the transfer in the ledger, even when the customer remembers it roughly.'],
  ['Explain', 'Checks for a keypad slip against frequent contacts, money already moving, and other complaints about the same wallet.'],
  ['Classify', 'Genuine wrong-send, scam victim, double-recovery claim, false claim or technical failure, with the reasons.'],
  ['Prioritise', 'Ranks the queue by the money likely to leave while a case waits, with the 10-working-day deadline as a floor.'],
  ['Recommend', 'A written rule picks the action and cites the procedure. A named person approves. Replies are drafted in Bangla and English.'],
]

const RULES = [
  ['10 working days to resolve', 'Sunday to Thursday, skipping public holidays, with the deadline on every case.', 'MFS Regulations 2022, §17.3'],
  ['Records kept 6 years', 'Every case, decision and reveal is stored with a hash chain that shows tampering.', '§18, §12.2'],
  ['No tipping off', 'Messages to the receiving wallet never mention fraud or a report.', 'MLPA 2012, §6'],
  ['Consent before processing', 'The customer sees the purpose, retention, who sees it and how to withdraw.', 'PDPO 2025'],
  ['No refund promises', 'The sender is responsible for the number; a return needs consent or legal process.', 'upay terms, §11.1'],
  ['People decide', 'Ferot recommends and drafts. It never moves money and never sends anything on its own.', 'Design rule R6'],
]

export default function Home({ go }: { go: (to: string) => void }) {
  const [metrics, setMetrics] = useState<Any | null>(null)
  const [sim, setSim] = useState<Any | null>(null)
  useEffect(() => {
    api.metrics().then(setMetrics).catch(() => {})
    api.simulation().then(setSim).catch(() => {})
  }, [])
  const s = metrics?.summary
  const g = metrics?.guard
  const q = sim?.summary

  return (
    <>
      <section className="bg-night text-paper">
        <div className="max-w-[1240px] mx-auto px-4 md:px-6 pt-12 pb-16 md:pt-16 md:pb-20 grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-12 lg:gap-16 items-start">
          <div className="lg:pt-6">
            <h1 className="text-[40px] md:text-[54px] font-semibold leading-[1.04] tracking-[-0.015em]">A wrong send is a race against cash‑out.</h1>
            <p className="mt-6 text-[17px] text-mist max-w-[34rem] leading-relaxed">
              Ferot warns customers before money goes to a mistyped or risky number. When it already has, Ferot reads the
              complaint, rebuilds where the money went, and puts the case whose money is about to leave at the top of the queue.
              People decide every action.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" tone="light" onClick={() => go('/customer')}>Try the customer app</Button>
              <Button size="lg" tone="outline-light" onClick={() => go('/console')}>Open the agent console</Button>
            </div>
          </div>

          <div>
            <figure className="bg-night-2 rounded-2xl p-6 md:p-8 border border-night-line">
              <figcaption className="text-[13px] text-mist">Complaint from Rahim, a shop owner in Rajshahi, sent in the app at 14:25</figcaption>
              <blockquote className="mt-4 font-display text-[26px] md:text-[34px] leading-[1.3] text-paper">
                bhai <Mark delay={500}>5000 taka</Mark> <Mark delay={900}>vul number</Mark> e chole gese, <Mark delay={1300}>01012-345687</Mark>, <Mark delay={1700}>ajke 2 tar dike</Mark>
              </blockquote>
              <dl className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3">
                {READ.map((r) => (
                  <div key={r.label} className="read-note" style={{ animationDelay: `${r.delay + 250}ms` }}>
                    <dt className="text-[12.5px] text-mist">{r.label}</dt>
                    <dd className="num text-[16px] text-paper">{r.value}</dd>
                  </div>
                ))}
              </dl>
            </figure>
            <div className="verdict relative -mt-3 mx-3 md:mx-6 bg-paper text-ink rounded-xl p-5 md:p-6 shadow-[0_18px_40px_-20px_rgba(0,0,0,0.6)]">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <TypeMark type="genuine_wrong_send" confidence={0.82} />
                <span className="text-[13px] text-ink-3">Ferot's reading, about two seconds later</span>
              </div>
              <div className="mt-4 overflow-x-auto">
                <NumberDiff intended="01012345678" actual="01012345687" positions={[9, 10]} revealed small />
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-4">
                <div><dt className="text-[12.5px] text-ink-3">Still holdable</dt><dd className="num text-[24px] leading-tight font-semibold text-flag">৳4,200</dd></div>
                <div><dt className="text-[12.5px] text-ink-3">Paid the right number</dt><dd className="num text-[24px] leading-tight font-semibold">11 times</dd></div>
                <div><dt className="text-[12.5px] text-ink-3">Complained after</dt><dd className="num text-[24px] leading-tight font-semibold">23 min</dd></div>
              </dl>
              <p className="mt-4 text-[14.5px] border-t border-line pt-3">
                Two digits were swapped. Recommended: hold ৳4,200 and ask the recipient to agree to return it. An agent approves.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-[1240px] mx-auto px-4 md:px-6 mt-16 grid grid-cols-1 md:grid-cols-2 gap-x-14 gap-y-12">
        <div>
          <h2 className="text-[28px] font-semibold">Before the money leaves</h2>
          <p className="mt-3 text-ink-2 max-w-[34rem]">
            Ferot Guard checks a transfer while the customer is still on the confirm screen. If the number is one keypad slip
            from someone they pay often, or the wallet looks like a scam drop, it says so in plain Bangla. The customer always decides.
          </p>
          <div className="mt-6 max-w-sm rounded-2xl border border-line bg-surface p-5 font-sans" lang="bn">
            <p className="font-display text-[20px] font-semibold">একটু থামুন</p>
            <p className="mt-2 text-[15px]">আপনি কি <span className="num font-semibold text-flag">01012345678</span> নম্বরে পাঠাতে চেয়েছিলেন? সেখানে আপনি আগে ১১ বার টাকা পাঠিয়েছেন।</p>
            <div className="mt-4 flex gap-2">
              <span className="flex-1 text-center rounded-lg bg-flag text-white py-2 text-[14px]">নম্বর বদলান</span>
              <span className="flex-1 text-center rounded-lg border border-line py-2 text-[14px]">তবুও পাঠান</span>
            </div>
          </div>
          {g && (
            <p className="mt-4 text-[14px] text-ink-2">
              On held-out test transfers it warned on <b className="num">{Math.round(g.recall_at_warn * 100)}%</b> of scam sends and
              every typo, and interrupted <b className="num">{g.innocent_warned_per_100}</b> in 100 ordinary sends.
            </p>
          )}
        </div>
        <div>
          <h2 className="text-[28px] font-semibold">After it has gone</h2>
          <p className="mt-3 text-ink-2 max-w-[34rem]">
            The agent opens one case file instead of four systems: the transfer, where the money went next, how much is still
            holdable, what kind of case it is and why, the rule that applies, and replies ready to send in both languages.
          </p>
          <svg viewBox="0 0 360 120" className="mt-6 w-full max-w-sm" role="img" aria-label="Holdable money falls from ৳3,000 to ৳489 within 7 minutes of a scam transfer">
            <rect width="360" height="120" rx="14" fill="#0f2a24" />
            <path d="M24 24 H70 V90 H200" fill="none" stroke="#9fe0c3" strokeWidth="2.2" />
            <path d="M24 24 H70 V90 H200 V100 H24Z" fill="#9fe0c3" fillOpacity="0.3" />
            <path d="M24 24 H70 V90 H200 V24Z" fill="#ff9aa8" fillOpacity="0.28" />
            <path d="M200 90 L336 99" stroke="#e3a008" strokeWidth="2" strokeDasharray="6 5" />
            <line x1="200" x2="200" y1="16" y2="100" stroke="#f4f7f5" strokeWidth="1.5" />
            <text x="24" y="114" fontSize="11" fill="#a9bdb6">Sent ৳3,000</text>
            <text x="200" y="114" fontSize="11" fill="#f4f7f5" textAnchor="middle">Complaint</text>
            <text x="78" y="56" fontSize="11" fill="#ff9aa8">−৳2,820 cash-out, 7 min</text>
          </svg>
          {s && (
            <p className="mt-4 text-[14px] text-ink-2">
              The case classifier scores a macro-F1 of <b className="num">{s.m4_macro_f1.toFixed(2)}</b> where keyword rules
              score <b className="num">{s.keyword_baseline_macro_f1.toFixed(2)}</b>, because text alone cannot tell a typo from a false claim.
            </p>
          )}
        </div>
      </section>

      <section className="max-w-[1240px] mx-auto px-4 md:px-6 mt-20">
        <h2 className="text-[28px] font-semibold">What happens to a complaint</h2>
        <ol className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-10 gap-y-8">
          {STEPS.map(([title, text], i) => (
            <li key={title} className="grid grid-cols-[2.25rem_1fr] gap-x-3">
              <span className="num text-[28px] leading-none text-turmeric font-semibold">{i + 1}</span>
              <div>
                <h3 className="text-[18px] font-semibold">{title}</h3>
                <p className="mt-1.5 text-[14.5px] text-ink-2">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="max-w-[1240px] mx-auto px-4 md:px-6 mt-20 grid grid-cols-1 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] gap-10">
        <div>
          <h2 className="text-[28px] font-semibold">Built to Bangladesh's MFS rules</h2>
          <p className="mt-3 text-ink-2">Each rule maps to code and a test. The full mapping is in the repository's compliance document.</p>
        </div>
        <dl className="grid sm:grid-cols-2 gap-x-10 gap-y-6">
          {RULES.map(([title, text, cite]) => (
            <div key={title} className="border-t-2 border-ink pt-3">
              <dt className="font-semibold text-[16px]">{title}</dt>
              <dd className="mt-1 text-[14.5px] text-ink-2">{text}</dd>
              <dd className="mt-1 text-[13px] text-ink-3">{cite}</dd>
            </div>
          ))}
        </dl>
      </section>

      {s && q && (
        <section className="max-w-[1240px] mx-auto px-4 md:px-6 mt-20">
          <div className="rounded-2xl bg-turmeric-soft px-6 py-7 md:px-10 grid grid-cols-1 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] gap-8 items-start">
            <div>
              <h2 className="text-[24px] font-semibold text-ink">Honest about the numbers</h2>
              <p className="mt-2 text-[14.5px] text-turmeric-ink">
                Everything is measured on synthetic data with a time-based split. Real upay data will be harder, and the evidence
                page shows where Ferot loses.
              </p>
              <button onClick={() => go('/analyst')} className="link mt-3 text-[14.5px]">See the evidence and the failures</button>
            </div>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div><dt className="text-[13px] text-turmeric-ink">Scams held at the policy threshold</dt><dd className="num text-[30px] font-semibold">{Math.round(s.m4_scam_recall_at_policy * 100)}%</dd></div>
              <div><dt className="text-[13px] text-turmeric-ink">Money recovered vs first come, first served</dt><dd className="num text-[30px] font-semibold">+{q.ferot.gain_vs_fcfs_pct}%</dd></div>
              <div><dt className="text-[13px] text-turmeric-ink">Largest-amount-first, for comparison</dt><dd className="num text-[30px] font-semibold">+{q.largest.gain_vs_fcfs_pct}%</dd></div>
              <div><dt className="text-[13px] text-turmeric-ink">Ceiling if we knew the future</dt><dd className="num text-[30px] font-semibold">+{q.oracle.gain_vs_fcfs_pct}%</dd></div>
            </dl>
          </div>
          <p className="mt-3 text-[13px] text-ink-3">
            Queue results: {sim.cases} held-out cases, {sim.assumptions.agents} agents, {sim.assumptions.seeds} runs. Ferot's ordering
            recovers {taka(q.ferot.gain_vs_fcfs)} more than first come, first served; a simple largest-first rule does about as well on this data.
          </p>
        </section>
      )}
    </>
  )
}
