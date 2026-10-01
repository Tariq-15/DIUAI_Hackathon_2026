import { useEffect, useState } from 'react'
import { api, type CustomerStatus, type DemoCustomer } from '../api'
import { taka, when } from '../lib'

type Lang = 'bn' | 'en'
type Step = 'pick' | 'help' | 'tx' | 'text' | 'consent' | 'done'

const T = {
  title: { bn: 'সমস্যা জানান', en: 'Report a problem' },
  howTo: { bn: 'কীভাবে অভিযোগ করবেন: সমস্যার ধরন বাছুন, লেনদেনটি বেছে নিন, সংক্ষেপে লিখুন।', en: 'How to report: choose the problem, pick the transaction, describe it briefly.' },
  problems: {
    wrong_number: { bn: 'ভুল নম্বরে টাকা গেছে', en: 'Money went to the wrong number' },
    scam: { bn: 'মনে হচ্ছে প্রতারিত হয়েছি', en: 'I think I was scammed' },
    failed: { bn: 'টাকা কেটেছে কিন্তু পৌঁছায়নি', en: 'Money deducted but not received' },
    agent: { bn: 'এজেন্ট পয়েন্টে সমস্যা', en: 'Problem at an agent point' },
  },
  pickTx: { bn: 'কোন লেনদেন নিয়ে অভিযোগ?', en: 'Which transaction is this about?' },
  describe: { bn: 'সংক্ষেপে লিখুন (বাংলা, ইংরেজি বা Banglish)', en: 'Describe it briefly (Bangla, English or Banglish)' },
  next: { bn: 'পরবর্তী', en: 'Next' },
  notice: {
    bn: 'আপনার অভিযোগ প্রক্রিয়া করতে আমরা আপনার লেখা বিবরণ ও লেনদেনের তথ্য ব্যবহার করব। উদ্দেশ্য: বিরোধ নিষ্পত্তি ও প্রতারণা প্রতিরোধ। সংরক্ষণ: অন্তত ৬ বছর (বাংলাদেশ ব্যাংকের নিয়ম)। কারা দেখবেন: গ্রাহকসেবা, প্রতারণা প্রতিরোধ ও কমপ্লায়েন্স টিম। ১৬২৬৮ নম্বরে কল করে পরবর্তী প্রক্রিয়ার সম্মতি প্রত্যাহার করতে পারেন; আইন অনুযায়ী যে রেকর্ড রাখতে হয় তা রাখা হবে।',
    en: 'To handle your complaint we will use what you write and your transaction records. Purpose: resolving the dispute and preventing fraud. Kept for at least 6 years, as Bangladesh Bank requires. Seen by: customer service, fraud prevention and compliance teams. You can withdraw consent for further processing by calling 16268; records the law requires us to keep are still kept.',
  },
  responsibility: {
    bn: 'মনে রাখবেন: সঠিক নম্বরে টাকা পাঠানোর দায়িত্ব প্রেরকের। অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে। ১০ কর্মদিবসের মধ্যে আমরা আপনাকে জানাব। সন্তুষ্ট না হলে বাংলাদেশ ব্যাংকে অভিযোগ করতে পারবেন।',
    en: 'Please note: the sender is responsible for entering the right number, and a return depends on the recipient\'s consent or legal process. We will update you within 10 working days. If you are not satisfied, you can complain to Bangladesh Bank.',
  },
  agree: { bn: 'আমি পড়েছি এবং সম্মতি দিচ্ছি', en: 'I have read this and agree' },
  submit: { bn: 'অভিযোগ জমা দিন', en: 'Submit complaint' },
  received: { bn: 'অভিযোগ গ্রহণ করা হয়েছে', en: 'Complaint received' },
  safety: { bn: 'উপায় কখনো আপনার পিন বা ওটিপি চায় না।', en: 'upay never asks for your PIN or OTP.' },
  steps: { bn: ['গৃহীত', 'পর্যালোচনা চলছে', 'পদক্ষেপ নেওয়া হয়েছে', 'নিষ্পত্তি'], en: ['Received', 'Under review', 'Action taken', 'Resolved'] },
  contest: { bn: 'সিদ্ধান্তে আপত্তি জানান (মানুষের পর্যালোচনা চাই)', en: 'Contest the outcome (ask for a human review)' },
}

export default function Customer() {
  const [lang, setLang] = useState<Lang>('bn')
  const [customers, setCustomers] = useState<DemoCustomer[]>([])
  const [who, setWho] = useState<DemoCustomer | null>(null)
  const [step, setStep] = useState<Step>('pick')
  const [problem, setProblem] = useState('wrong_number')
  const [trx, setTrx] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [status, setStatus] = useState<CustomerStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.demoCustomers().then(setCustomers).catch((e) => setError(String(e)))
  }, [])

  const t = (k: keyof typeof T) => (T[k] as Record<Lang, string>)[lang]

  async function submit() {
    if (!who) return
    setBusy(true)
    setError('')
    try {
      const res = await api.createComplaint({
        claimant: who.wallet, text, channel: 'app', problem, trx_id: trx,
        consent: { accepted: agreed, version: '2026-10-01', language: lang }, as_of_minute: who.now_minute,
      })
      setStatus(res.status)
      setStep('done')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  async function contest() {
    if (!status) return
    setStatus(await api.contest(status.case_id, lang === 'bn' ? 'গ্রাহক মানুষের পর্যালোচনা চান' : 'Customer asks for a human review'))
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 grid md:grid-cols-[380px_1fr] gap-8">
      <div className="mx-auto w-[360px] rounded-[2.2rem] bg-slate-900 p-3 shadow-xl">
        <div className={`rounded-[1.8rem] bg-white min-h-[640px] overflow-hidden flex flex-col ${lang === 'bn' ? 'bn' : ''}`}>
          <div className="bg-teal-700 text-white px-5 pt-6 pb-4">
            <div className="flex items-center justify-between text-xs opacity-80">
              <span>Wallet app mock · prototype</span>
              <button onClick={() => setLang(lang === 'bn' ? 'en' : 'bn')} className="underline">{lang === 'bn' ? 'English' : 'বাংলা'}</button>
            </div>
            <h2 className="text-lg font-semibold mt-2">{t('title')}</h2>
            {who && <p className="text-xs opacity-80 mt-0.5">{who.label} · {who.wallet}</p>}
          </div>
          <div className="flex-1 p-4 space-y-3 text-sm">
            {error && <p className="text-rose-700 bg-rose-50 rounded p-2 text-xs">{error}</p>}
            {step === 'pick' && (
              <>
                <p className="text-slate-600 text-xs">Demo: choose a synthetic customer.</p>
                {customers.map((c) => (
                  <button key={c.key} onClick={() => { setWho(c); setText(c.sample_text); setStep('help') }}
                    className="w-full text-left p-3 rounded-xl ring-1 ring-slate-200 hover:bg-slate-50">
                    <div className="font-medium">{c.label}</div>
                    <div className="text-xs text-slate-500">{c.wallet} · {when(c.now)}</div>
                  </button>
                ))}
              </>
            )}
            {step === 'help' && (
              <>
                <p className="text-xs text-slate-600">{t('howTo')}</p>
                {(Object.keys(T.problems) as (keyof typeof T.problems)[]).map((k) => (
                  <button key={k} onClick={() => { setProblem(k); setStep('tx') }}
                    className="w-full text-left p-3 rounded-xl ring-1 ring-slate-200 hover:bg-teal-50">{T.problems[k][lang]}</button>
                ))}
              </>
            )}
            {step === 'tx' && who && (
              <>
                <p className="font-medium">{t('pickTx')}</p>
                <div className="space-y-2 max-h-[420px] overflow-y-auto">
                  {who.transactions.map((x) => (
                    <button key={x.trx_id} onClick={() => { setTrx(x.trx_id); setStep('text') }}
                      className={`w-full text-left p-2.5 rounded-lg ring-1 ${trx === x.trx_id ? 'ring-teal-600 bg-teal-50' : 'ring-slate-200'}`}>
                      <div className="flex justify-between"><span>{x.type.replace('_', ' ')} → {x.to}</span><span className="font-semibold">{taka(x.amount)}</span></div>
                      <div className="text-xs text-slate-500">{when(x.ts)} · {x.trx_id}</div>
                    </button>
                  ))}
                </div>
                <button onClick={() => { setTrx(null); setStep('text') }} className="text-xs underline text-slate-600">Not in the list</button>
              </>
            )}
            {step === 'text' && (
              <>
                <label className="font-medium block">{t('describe')}</label>
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} className="w-full rounded-lg ring-1 ring-slate-300 p-2 text-sm" />
                <button onClick={() => setStep('consent')} disabled={text.trim().length < 3} className="w-full py-2 rounded-lg bg-teal-700 text-white disabled:opacity-50">{t('next')}</button>
              </>
            )}
            {step === 'consent' && (
              <>
                <div className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed">{t('notice')}</div>
                <div className="rounded-lg bg-amber-50 p-3 text-xs leading-relaxed text-amber-950">{t('responsibility')}</div>
                <label className="flex gap-2 items-start text-xs">
                  <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5" />
                  {t('agree')}
                </label>
                <button onClick={submit} disabled={!agreed || busy} className="w-full py-2 rounded-lg bg-teal-700 text-white disabled:opacity-50">{busy ? '…' : t('submit')}</button>
              </>
            )}
            {step === 'done' && status && (
              <>
                <div className="rounded-xl bg-emerald-50 p-3">
                  <p className="font-semibold text-emerald-900">{t('received')}</p>
                  <p className="text-xs text-emerald-900 mt-1">#{status.case_id}</p>
                </div>
                <ol className="space-y-1.5">
                  {T.steps[lang].map((s, i) => (
                    <li key={s} className="flex items-center gap-2 text-xs">
                      <span className={`w-5 h-5 rounded-full grid place-items-center text-[10px] ${i < status.step ? 'bg-teal-700 text-white' : 'bg-slate-200 text-slate-500'}`}>{i + 1}</span>
                      {s}
                    </li>
                  ))}
                </ol>
                <p className="text-xs leading-relaxed">{lang === 'bn' ? status.message_bn : status.message_en}</p>
                <p className="text-xs text-slate-600">{status.escalation}</p>
                <p className="text-xs font-medium text-rose-700">{t('safety')}</p>
                <div className="flex gap-2">
                  <button onClick={async () => setStatus(await api.status(status.case_id))} className="text-xs underline">Refresh</button>
                  {status.can_contest && <button onClick={contest} className="text-xs underline text-rose-700">{t('contest')}</button>}
                </div>
                <button onClick={() => { setStep('pick'); setWho(null); setStatus(null); setAgreed(false); setTrx(null) }} className="text-xs text-slate-500 underline">Start again</button>
              </>
            )}
          </div>
          <p className="text-[10px] text-center text-slate-400 pb-2">Prototype · not an upay message</p>
        </div>
      </div>
      <aside className="space-y-4 text-sm text-slate-700">
        <h2 className="text-xl font-semibold text-slate-900">Customer intake</h2>
        <p>The customer picks the transaction from their history, which removes most extraction errors, and writes a few words in any language.</p>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Consent and notice (R8, PDPO 2025):</b> purpose, retention, who sees it and how to withdraw, before anything is processed.</li>
          <li><b>Responsibilities (R1, R4):</b> upay's terms make the sender responsible for the number; a return needs the recipient's consent or legal process.</li>
          <li><b>Timeline (MFS Regulations §17.3):</b> 10 working days, Sunday to Thursday, skipping public holidays.</li>
          <li><b>Escalation (§17.4):</b> Bangladesh Bank's customer complaint channel is named on every status screen.</li>
          <li><b>Contest (R6):</b> the customer can ask for a human-only review of the outcome.</li>
        </ul>
        <p className="text-xs text-slate-500">After submitting, open the agent console to see the case appear in the queue.</p>
      </aside>
    </div>
  )
}
