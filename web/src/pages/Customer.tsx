import { type ReactNode, useEffect, useState } from 'react'
import { api, type CustomerStatus, type DemoCustomer, type GuardCheck } from '../api'
import { Button, NumberDiff } from '../components'
import { bnNum, taka, when } from '../lib'

type Lang = 'bn' | 'en'
type Tab = 'send' | 'report'
type SendStep = 'form' | 'confirm' | 'sheet' | 'sent' | 'cancelled'
type ReportStep = 'help' | 'tx' | 'text' | 'consent' | 'done'
type Any = Record<string, any>

const T = {
  send: { bn: 'টাকা পাঠান', en: 'Send money' },
  report: { bn: 'সমস্যা জানান', en: 'Report a problem' },
  choose: { bn: 'ডেমো গ্রাহক বেছে নিন', en: 'Choose a demo customer' },
  chooseNote: { bn: 'সব গ্রাহক ও নম্বর কাল্পনিক।', en: 'All customers and numbers are synthetic.' },
  balanceNote: { bn: 'ডেমো: কোনো টাকা আসলে যায় না।', en: 'Demo: no money actually moves.' },
  quick: { bn: 'দ্রুত বেছে নিন', en: 'Quick pick' },
  number: { bn: 'প্রাপকের নম্বর', en: "Recipient's number" },
  amount: { bn: 'পরিমাণ (৳)', en: 'Amount (৳)' },
  numberHelp: { bn: '০১ দিয়ে শুরু ১১ সংখ্যার নম্বর', en: '11 digits starting with 01' },
  next: { bn: 'পরবর্তী', en: 'Next' },
  checking: { bn: 'যাচাই হচ্ছে…', en: 'Checking…' },
  confirmTitle: { bn: 'নিশ্চিত করুন', en: 'Confirm' },
  to: { bn: 'প্রাপক', en: 'To' },
  confirmSend: { bn: 'নিশ্চিত করে পাঠান', en: 'Confirm and send' },
  pinNote: { bn: 'ডেমোতে পিন লাগবে না।', en: 'No PIN in this demo.' },
  warnTitle: { bn: 'একটু থামুন', en: 'Check before you send' },
  reviewTitle: { bn: 'এই লেনদেনটি ঝুঁকিপূর্ণ মনে হচ্ছে', en: 'This transfer looks risky' },
  didYouMean: { bn: 'আপনি কি এই নম্বরে পাঠাতে চেয়েছিলেন?', en: 'Did you mean this number?' },
  usual: { bn: 'আগে পাঠিয়েছেন', en: 'You usually pay' },
  typed: { bn: 'এখন লিখেছেন', en: 'You typed' },
  change: { bn: 'নম্বর বদলান', en: 'Use this number' },
  cancel: { bn: 'বাতিল করুন', en: 'Cancel' },
  sendAnyway: { bn: 'তবুও পাঠান', en: 'Send anyway' },
  wait: { bn: 'অপেক্ষা করুন', en: 'Wait' },
  pauseNote: { bn: 'ঝুঁকিপূর্ণ লেনদেনে ৩০ সেকেন্ড ভাবার সময় দেওয়া হয়।', en: 'Risky transfers get a 30-second pause to think.' },
  youDecide: { bn: 'সিদ্ধান্ত আপনার। উপায় লেনদেন আটকায় না।', en: 'You decide. The transfer is never blocked.' },
  sent: { bn: 'টাকা পাঠানো হয়েছে', en: 'Money sent' },
  sentMistake: { bn: 'ভুল হয়ে থাকলে এখনই জানান। যত তাড়াতাড়ি জানাবেন, তত বেশি টাকা আটকানো যেতে পারে।', en: 'If this was a mistake, report it now. The sooner you report, the more money can be held.' },
  reportNow: { bn: 'এখনই সমস্যা জানান', en: 'Report a problem now' },
  cancelled: { bn: 'পাঠানো হয়নি', en: 'Not sent' },
  cancelledNote: { bn: 'আপনার ওয়ালেট থেকে কোনো টাকা যায়নি।', en: 'Nothing left your wallet.' },
  again: { bn: 'আবার শুরু করুন', en: 'Start again' },
  howTo: { bn: 'সমস্যার ধরন বাছুন, লেনদেনটি বেছে নিন, তারপর সংক্ষেপে লিখুন।', en: 'Choose the problem, pick the transaction, then describe it briefly.' },
  pickTx: { bn: 'কোন লেনদেন নিয়ে অভিযোগ?', en: 'Which transaction is this about?' },
  notListed: { bn: 'তালিকায় নেই', en: 'It is not in the list' },
  describe: { bn: 'সংক্ষেপে লিখুন (বাংলা, ইংরেজি বা Banglish)', en: 'Describe it briefly (Bangla, English or Banglish)' },
  notice: {
    bn: 'আপনার অভিযোগ প্রক্রিয়া করতে আমরা আপনার লেখা বিবরণ ও লেনদেনের তথ্য ব্যবহার করব। উদ্দেশ্য: বিরোধ নিষ্পত্তি ও প্রতারণা প্রতিরোধ। সংরক্ষণ: অন্তত ৬ বছর (বাংলাদেশ ব্যাংকের নিয়ম)। কারা দেখবেন: গ্রাহকসেবা, প্রতারণা প্রতিরোধ ও কমপ্লায়েন্স টিম। ১৬২৬৮ নম্বরে কল করে পরবর্তী প্রক্রিয়ার সম্মতি প্রত্যাহার করতে পারেন; আইন অনুযায়ী যে রেকর্ড রাখতে হয় তা রাখা হবে।',
    en: 'To handle your complaint we will use what you write and your transaction records. Purpose: resolving the dispute and preventing fraud. Kept for at least 6 years, as Bangladesh Bank requires. Seen by: customer service, fraud prevention and compliance teams. You can withdraw consent for further processing by calling 16268; records the law requires us to keep are still kept.',
  },
  responsibility: {
    bn: 'মনে রাখবেন: সঠিক নম্বরে টাকা পাঠানোর দায়িত্ব প্রেরকের। অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে। ১০ কর্মদিবসের মধ্যে আমরা আপনাকে জানাব। সন্তুষ্ট না হলে বাংলাদেশ ব্যাংকে অভিযোগ করতে পারবেন।',
    en: "Please note: the sender is responsible for entering the right number, and a return depends on the recipient's consent or legal process. We will update you within 10 working days. If you are not satisfied, you can complain to Bangladesh Bank.",
  },
  agree: { bn: 'আমি পড়েছি এবং সম্মতি দিচ্ছি', en: 'I have read this and agree' },
  submit: { bn: 'অভিযোগ জমা দিন', en: 'Submit complaint' },
  received: { bn: 'অভিযোগ গ্রহণ করা হয়েছে', en: 'Complaint received' },
  safety: { bn: 'উপায় কখনো আপনার পিন বা ওটিপি চায় না।', en: 'upay never asks for your PIN or OTP.' },
  steps: { bn: ['গৃহীত', 'পর্যালোচনা চলছে', 'পদক্ষেপ নেওয়া হয়েছে', 'নিষ্পত্তি'], en: ['Received', 'Under review', 'Action taken', 'Resolved'] },
  contest: { bn: 'সিদ্ধান্তে আপত্তি জানান', en: 'Ask for a human review' },
  refresh: { bn: 'হালনাগাদ দেখুন', en: 'Check for updates' },
  problems: {
    wrong_number: { bn: 'ভুল নম্বরে টাকা গেছে', en: 'Money went to the wrong number' },
    scam: { bn: 'মনে হচ্ছে প্রতারিত হয়েছি', en: 'I think I was scammed' },
    failed: { bn: 'টাকা কেটেছে কিন্তু পৌঁছায়নি', en: 'Money deducted but not received' },
    agent: { bn: 'এজেন্ট পয়েন্টে সমস্যা', en: 'Problem at an agent point' },
  },
}

const SCENARIO_BN: Record<string, string> = { usual: 'ভাইকে নিয়মিত পাঠানো টাকা', risky: 'যে লেনদেনটি ভুল হয়েছিল' }
const toAscii = (s: string) => s.replace(/[০-৯]/g, (d) => String('০১২৩৪৫৬৭৮৯'.indexOf(d))).replace(/[\s-]/g, '')

function Phone({ children, lang, title, time, onBack, onLang, tab, onTab, showTabs }: {
  children: ReactNode; lang: Lang; title: string; time: string; onBack?: () => void; onLang: () => void; tab: Tab; onTab: (t: Tab) => void; showTabs: boolean
}) {
  return (
    <div className="mx-auto w-full max-w-[372px] rounded-[2.6rem] bg-ink p-[10px] shadow-[0_30px_60px_-30px_rgba(15,42,36,0.55)]">
      <div lang={lang} className="relative rounded-[2.1rem] bg-paper h-[720px] overflow-hidden flex flex-col">
        <div className="bg-night text-paper px-5 pt-3 pb-4">
          <div className="flex items-center justify-between text-[12px] text-mist">
            <span className="num">{lang === 'bn' ? bnNum(time) : time}</span>
            <span className="w-20 h-5 rounded-full bg-ink" aria-hidden="true" />
            <button onClick={onLang} className="underline underline-offset-2 hover:text-paper">{lang === 'bn' ? 'English' : 'বাংলা'}</button>
          </div>
          <div className="mt-3 flex items-center gap-2">
            {onBack && (
              <button onClick={onBack} aria-label={lang === 'bn' ? 'পেছনে' : 'Back'} className="-ml-1 w-8 h-8 grid place-items-center rounded-full hover:bg-night-2">
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5 8 12l7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            )}
            <h2 className="text-[21px] font-semibold">{title}</h2>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
        {showTabs && (
          <nav className="grid grid-cols-2 border-t border-line bg-surface" aria-label="Wallet app">
            {(['send', 'report'] as Tab[]).map((t) => (
              <button key={t} onClick={() => onTab(t)} aria-current={tab === t ? 'page' : undefined}
                className={`py-3 text-[14px] flex flex-col items-center gap-1 ${tab === t ? 'text-flag font-semibold' : 'text-ink-3'}`}>
                {t === 'send'
                  ? <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h13m0 0-5-5m5 5-5 5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  : <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10m0 4v.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>}
                {T[t][lang]}
              </button>
            ))}
          </nav>
        )}
      </div>
    </div>
  )
}

export default function Customer({ go }: { go: (to: string) => void }) {
  const [lang, setLang] = useState<Lang>('bn')
  const [customers, setCustomers] = useState<DemoCustomer[]>([])
  const [who, setWho] = useState<DemoCustomer | null>(null)
  const [tab, setTab] = useState<Tab>('send')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [metrics, setMetrics] = useState<Any | null>(null)
  // send
  const [sendStep, setSendStep] = useState<SendStep>('form')
  const [recipient, setRecipient] = useState('')
  const [amount, setAmount] = useState('')
  const [minute, setMinute] = useState<number | undefined>(undefined)
  const [check, setCheck] = useState<GuardCheck | null>(null)
  const [countdown, setCountdown] = useState(0)
  // report
  const [step, setStep] = useState<ReportStep>('help')
  const [problem, setProblem] = useState('wrong_number')
  const [trx, setTrx] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [status, setStatus] = useState<CustomerStatus | null>(null)

  useEffect(() => {
    api.demoCustomers().then(setCustomers).catch((e) => setError(String(e.message ?? e)))
    api.metrics().then(setMetrics).catch(() => {})
  }, [])
  useEffect(() => {
    if (countdown <= 0) return
    const id = window.setTimeout(() => setCountdown((c) => c - 1), 1000)
    return () => window.clearTimeout(id)
  }, [countdown])

  const t = (k: Exclude<keyof typeof T, 'steps' | 'problems'>) => T[k][lang]
  const n = (s: string | number) => (lang === 'bn' ? bnNum(s) : String(s))
  const money = (v: number) => n(taka(v))

  function pick(c: DemoCustomer) {
    setWho(c)
    setText(c.sample_text)
    const risky = c.send_scenarios.find((s) => s.key === 'usual') ?? c.send_scenarios[0]
    setRecipient(risky?.recipient ?? '')
    setAmount(risky ? String(risky.amount) : '')
    setMinute(risky?.minute)
    resetFlows()
  }
  function resetFlows() {
    setSendStep('form'); setCheck(null); setCountdown(0)
    setStep('help'); setTrx(null); setAgreed(false); setStatus(null); setError('')
  }

  const cleanNumber = toAscii(recipient)
  const amt = Number(toAscii(amount))
  const formOk = /^01\d{9}$/.test(cleanNumber) && amt > 0 && amt <= 25000

  async function runCheck(number = cleanNumber) {
    if (!who) return
    setBusy(true); setError('')
    try {
      const res = await api.guardCheck({ sender: who.wallet, recipient: number, amount: amt, as_of_minute: minute ?? who.send_minute })
      setCheck(res)
      if (res.band === 'allow') setSendStep('confirm')
      else {
        setSendStep('sheet')
        setCountdown(res.band === 'review' ? 30 : 0)
      }
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function decide(decision: 'cancelled' | 'sent_anyway' | 'changed_number') {
    if (!check) return
    await api.guardDecision(check.check_id, decision).catch(() => {})
    if (decision === 'cancelled') setSendStep('cancelled')
    else if (decision === 'sent_anyway') setSendStep('sent')
    else if (check.typo) {
      setRecipient(check.typo.candidate)
      await runCheck(check.typo.candidate)
    }
  }

  async function submit() {
    if (!who) return
    setBusy(true); setError('')
    try {
      const res = await api.createComplaint({
        claimant: who.wallet, text, channel: 'app', problem, trx_id: trx,
        consent: { accepted: agreed, version: '2026-10-01', language: lang }, as_of_minute: who.now_minute,
      })
      setStatus(res.status)
      setStep('done')
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  const back = !who ? undefined
    : tab === 'send' ? (sendStep === 'confirm' ? () => setSendStep('form') : sendStep === 'form' ? () => setWho(null) : undefined)
      : ({ help: () => setWho(null), tx: () => setStep('help'), text: () => setStep('tx'), consent: () => setStep('text'), done: undefined } as Record<ReportStep, (() => void) | undefined>)[step]

  const phoneTime = who
    ? new Date(new Date(who.now).getTime() - (who.now_minute - (tab === 'send' ? minute ?? who.send_minute : who.now_minute)) * 60000)
      .toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    : '14:00'
  const title = !who ? 'Ferot' : tab === 'send' ? (sendStep === 'confirm' ? t('confirmTitle') : t('send')) : t('report')

  return (
    <div className="max-w-[1240px] mx-auto px-4 md:px-6 py-10 grid grid-cols-1 lg:grid-cols-[400px_minmax(0,1fr)] gap-12">
      <div>
        <Phone lang={lang} title={title} time={phoneTime} onBack={back} onLang={() => setLang(lang === 'bn' ? 'en' : 'bn')} tab={tab}
          onTab={(x) => { setTab(x); setError('') }} showTabs={!!who}>
          <div className="p-5 space-y-4 text-[15px]">
            {error && <p className="rounded-lg bg-signal-soft text-signal-2 px-3 py-2 text-[13.5px]">{error}</p>}

            {!who && (
              <>
                <div>
                  <p className="font-semibold text-[16px]">{t('choose')}</p>
                  <p className="text-[13.5px] text-ink-3">{t('chooseNote')}</p>
                </div>
                {customers.map((c) => (
                  <button key={c.key} onClick={() => pick(c)} className="w-full text-left rounded-xl bg-surface border border-line px-4 py-3.5 hover:border-flag transition-colors">
                    <span className="block font-semibold">{c.label}</span>
                    <span className="block num text-[13.5px] text-ink-3 mt-0.5">{n(c.wallet)}</span>
                  </button>
                ))}
                {!customers.length && !error && <p className="text-ink-3 text-[14px]">…</p>}
              </>
            )}

            {who && tab === 'send' && sendStep === 'form' && (
              <>
                {who.send_scenarios.length > 0 && (
                  <div>
                    <p className="text-[13px] text-ink-3 mb-2">{t('quick')}</p>
                    <div className="flex flex-wrap gap-2">
                      {who.send_scenarios.map((s) => {
                        const on = cleanNumber === s.recipient && amt === s.amount
                        return (
                          <button key={s.key} onClick={() => { setRecipient(s.recipient); setAmount(String(s.amount)); setMinute(s.minute) }}
                            className={`rounded-full px-3 py-1.5 text-[13.5px] border ${on ? 'bg-flag text-white border-flag' : 'bg-surface border-line hover:border-flag'}`}>
                            {lang === 'bn' ? SCENARIO_BN[s.key] ?? s.label : s.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                <label className="block">
                  <span className="text-[14px] font-medium">{t('number')}</span>
                  <input value={recipient} onChange={(e) => setRecipient(e.target.value)} inputMode="numeric" autoComplete="off"
                    className="field mt-1 num text-[20px] tracking-wide" placeholder="01XXXXXXXXX" aria-describedby="num-help" />
                  <span id="num-help" className="text-[12.5px] text-ink-3">{t('numberHelp')}</span>
                </label>
                <label className="block">
                  <span className="text-[14px] font-medium">{t('amount')}</span>
                  <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="numeric" className="field mt-1 num text-[20px]" />
                </label>
                <Button className="w-full" size="lg" disabled={!formOk || busy} onClick={() => runCheck()}>{busy ? t('checking') : t('next')}</Button>
                <p className="text-[12.5px] text-ink-3 text-center">{t('balanceNote')}</p>
              </>
            )}

            {who && tab === 'send' && sendStep === 'confirm' && check && (
              <>
                <div className="rounded-xl bg-surface border border-line p-4">
                  <p className="text-[13px] text-ink-3">{t('to')}</p>
                  <p className="num text-[22px] font-semibold">{n(check.recipient)}</p>
                  <p className="num text-[34px] font-semibold mt-2">{money(check.amount)}</p>
                </div>
                <Button className="w-full" size="lg" onClick={() => setSendStep('sent')}>{t('confirmSend')}</Button>
                <p className="text-[12.5px] text-ink-3 text-center">{t('pinNote')} {t('balanceNote')}</p>
              </>
            )}

            {who && tab === 'send' && sendStep === 'sent' && check && (
              <>
                <div className="rounded-xl bg-flag-soft p-4">
                  <p className="font-semibold text-flag-2 text-[17px]">{t('sent')}</p>
                  <p className="num mt-1">{money(check.amount)} → {n(check.recipient)}</p>
                </div>
                {check.decision === 'sent_anyway' || check.band !== 'allow' ? (
                  <div className="rounded-xl border border-line bg-surface p-4">
                    <p className="text-[14.5px]">{t('sentMistake')}</p>
                    <Button tone="secondary" className="w-full mt-3" onClick={() => { setTab('report'); setStep('help') }}>{t('reportNow')}</Button>
                  </div>
                ) : null}
                <button className="link text-[14px]" onClick={() => { setSendStep('form'); setCheck(null) }}>{t('again')}</button>
              </>
            )}

            {who && tab === 'send' && sendStep === 'cancelled' && (
              <>
                <div className="rounded-xl bg-surface border border-line p-4">
                  <p className="font-semibold text-[17px]">{t('cancelled')}</p>
                  <p className="text-ink-2 mt-1">{t('cancelledNote')}</p>
                </div>
                <button className="link text-[14px]" onClick={() => { setSendStep('form'); setCheck(null) }}>{t('again')}</button>
              </>
            )}

            {who && tab === 'report' && step === 'help' && (
              <>
                <p className="text-[14px] text-ink-2">{t('howTo')}</p>
                {(Object.keys(T.problems) as (keyof typeof T.problems)[]).map((k) => (
                  <button key={k} onClick={() => { setProblem(k); setStep('tx') }}
                    className="w-full text-left rounded-xl bg-surface border border-line px-4 py-3.5 hover:border-flag transition-colors">{T.problems[k][lang]}</button>
                ))}
              </>
            )}
            {who && tab === 'report' && step === 'tx' && (
              <>
                <p className="font-semibold">{t('pickTx')}</p>
                <div className="space-y-2">
                  {who.transactions.map((x) => (
                    <button key={x.trx_id} onClick={() => { setTrx(x.trx_id); setStep('text') }}
                      className={`w-full text-left rounded-xl bg-surface border px-4 py-3 ${trx === x.trx_id ? 'border-flag' : 'border-line hover:border-flag'}`}>
                      <span className="flex justify-between gap-3">
                        <span className="num">{n(x.to)}</span>
                        <span className="num font-semibold">{money(x.amount)}</span>
                      </span>
                      <span className="block text-[12.5px] text-ink-3 mt-0.5">{n(when(x.ts))}, {x.trx_id}</span>
                    </button>
                  ))}
                </div>
                <button onClick={() => { setTrx(null); setStep('text') }} className="link text-[14px]">{t('notListed')}</button>
              </>
            )}
            {who && tab === 'report' && step === 'text' && (
              <>
                <label className="block">
                  <span className="font-medium">{t('describe')}</span>
                  <textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} className="field mt-2 leading-relaxed" />
                </label>
                <Button className="w-full" size="lg" disabled={text.trim().length < 3} onClick={() => setStep('consent')}>{t('next')}</Button>
              </>
            )}
            {who && tab === 'report' && step === 'consent' && (
              <>
                <p className="rounded-xl bg-surface border border-line p-4 text-[13.5px] leading-relaxed">{t('notice')}</p>
                <p className="rounded-xl bg-turmeric-soft p-4 text-[13.5px] leading-relaxed text-turmeric-ink">{t('responsibility')}</p>
                <label className="flex gap-3 items-start text-[14.5px]">
                  <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-1 w-4 h-4 accent-[#006a4e]" />
                  {t('agree')}
                </label>
                <Button className="w-full" size="lg" disabled={!agreed || busy} onClick={submit}>{busy ? '…' : t('submit')}</Button>
              </>
            )}
            {who && tab === 'report' && step === 'done' && status && (
              <>
                <div className="rounded-xl bg-flag-soft p-4">
                  <p className="font-semibold text-flag-2 text-[17px]">{t('received')}</p>
                  <p className="num text-flag-2 mt-0.5">{status.case_id}</p>
                </div>
                <ol className="space-y-2.5">
                  {T.steps[lang].map((s, i) => (
                    <li key={s} className="flex items-center gap-3 text-[14.5px]">
                      <span className={`w-6 h-6 rounded-full grid place-items-center text-[12px] num ${i < status.step ? 'bg-flag text-white' : 'bg-paper-2 text-ink-3'}`}>{n(i + 1)}</span>
                      <span className={i < status.step ? 'font-medium' : 'text-ink-3'}>{s}</span>
                    </li>
                  ))}
                </ol>
                <p className="text-[14px] leading-relaxed">{lang === 'bn' ? status.message_bn : status.message_en}</p>
                <p className="text-[13px] text-ink-3">{status.escalation}</p>
                <p className="text-[14px] font-medium text-signal-2">{t('safety')}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  <button className="link text-[14px]" onClick={async () => setStatus(await api.status(status.case_id))}>{t('refresh')}</button>
                  {status.can_contest && (
                    <button className="link text-[14px]" onClick={async () => setStatus(await api.contest(status.case_id, lang === 'bn' ? 'গ্রাহক মানুষের পর্যালোচনা চান' : 'Customer asks for a human review'))}>{t('contest')}</button>
                  )}
                </div>
              </>
            )}
          </div>

          {who && tab === 'send' && sendStep === 'sheet' && check && (
            <div className="absolute inset-0 bg-ink/45 flex items-end" role="dialog" aria-modal="true" aria-labelledby="guard-title">
              <div className={`sheet-in w-full bg-surface rounded-t-[1.6rem] px-5 pt-5 pb-6 border-t-4 ${check.band === 'review' ? 'border-signal' : 'border-turmeric'} max-h-[88%] overflow-y-auto`}>
                <div className="flex items-start gap-3">
                  <span className={`mt-0.5 w-9 h-9 rounded-full grid place-items-center shrink-0 ${check.band === 'review' ? 'bg-signal text-white' : 'bg-turmeric text-ink'}`} aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24"><path d="M12 6v8m0 4v.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" /></svg>
                  </span>
                  <div>
                    <h3 id="guard-title" className="text-[20px] font-semibold leading-tight">{check.band === 'review' ? t('reviewTitle') : t('warnTitle')}</h3>
                    <p className="num text-[13.5px] text-ink-3 mt-1">{money(check.amount)} → {n(check.recipient)}</p>
                  </div>
                </div>

                {check.typo && (
                  <div className="mt-4 rounded-xl bg-paper p-3.5">
                    <p className="font-semibold text-[15px] mb-2.5 leading-snug">{(() => { const r = check.reasons.find((x) => x.key === 'typo'); return r ? (lang === 'bn' ? bnNum(r.bn) : r.en) : t('didYouMean') })()}</p>
                    <NumberDiff intended={check.typo.candidate} actual={check.recipient} positions={check.typo.positions} revealed small labels={[t('usual'), t('typed')]} />
                  </div>
                )}

                <ul className="mt-4 space-y-2">
                  {check.reasons.filter((r) => r.key !== 'typo').map((r) => (
                    <li key={r.key} className="flex gap-2.5 text-[14.5px] leading-snug">
                      <span className={`mt-[7px] w-1.5 h-1.5 rounded-full shrink-0 ${check.band === 'review' ? 'bg-signal' : 'bg-turmeric'}`} aria-hidden="true" />
                      {lang === 'bn' ? bnNum(r.bn) : r.en}
                    </li>
                  ))}
                </ul>

                {check.advice && check.band === 'review' && (
                  <p className="mt-4 rounded-xl bg-signal-soft text-signal-2 px-3.5 py-3 text-[14px] leading-snug">{check.advice[lang]}</p>
                )}

                <div className="mt-5 space-y-2.5">
                  {check.typo && <Button className="w-full" size="lg" onClick={() => decide('changed_number')}>{t('change')} {n(check.typo.candidate)}</Button>}
                  <Button className="w-full" size="lg" tone={check.typo ? 'secondary' : 'primary'} onClick={() => decide('cancelled')}>{t('cancel')}</Button>
                  <Button className="w-full" tone="quiet" disabled={countdown > 0} onClick={() => decide('sent_anyway')}>
                    {countdown > 0 ? `${t('sendAnyway')} (${n(countdown)})` : t('sendAnyway')}
                  </Button>
                </div>
                <p className="mt-3 text-[12.5px] text-ink-3 text-center">{check.band === 'review' ? `${t('pauseNote')} ` : ''}{t('youDecide')}</p>
              </div>
            </div>
          )}
        </Phone>
        <p className="mt-3 text-center text-[12.5px] text-ink-3">Wallet app mock for the prototype. Not an upay screen.</p>
      </div>

      <aside className="min-w-0">
        {tab === 'send' ? <GuardSide check={check} metrics={metrics} /> : <ReportSide go={go} done={step === 'done'} />}
      </aside>
    </div>
  )
}

function Gauge({ risk }: { risk: number }) {
  return (
    <div>
      <div className="relative">
        <div className="h-3 rounded-full overflow-hidden flex">
          <span className="h-full bg-flag-soft" style={{ width: '30%' }} />
          <span className="h-full bg-turmeric-soft" style={{ width: '40%' }} />
          <span className="h-full bg-signal-soft" style={{ width: '30%' }} />
        </div>
        <span className="absolute top-[-4px] w-[4px] h-[20px] bg-ink rounded" style={{ left: `calc(${Math.min(Math.max(risk, 0), 100)}% - ${risk >= 99 ? 4 : risk <= 1 ? 0 : 2}px)` }} />
      </div>
      <div className="flex text-[12px] text-ink-3 mt-1.5">
        <span style={{ width: '30%' }}>Allow</span>
        <span style={{ width: '40%' }}>Warn from 30</span>
        <span style={{ width: '30%' }}>Review from 70</span>
      </div>
    </div>
  )
}

const FEATURE_TEXT: [string, string, (v: number) => string][] = [
  ['first_ever', 'First transfer to this number', (v) => (v ? 'yes' : 'no')],
  ['n_prior_to_recipient', 'Earlier transfers to it', (v) => String(v)],
  ['recipient_age_days', 'Age of the receiving wallet', (v) => `${Math.round(v)} days`],
  ['prior_complainants_on_recipient', 'Others who complained about it', (v) => String(v)],
  ['recipient_distinct_senders_7d', 'Different senders in 7 days', (v) => String(v)],
  ['recipient_passthrough_30d', 'Cashed out vs received, 30 days', (v) => `${v.toFixed(1)}×`],
]

function GuardSide({ check, metrics }: { check: GuardCheck | null; metrics: Any | null }) {
  const g = metrics?.guard
  const fair = g?.fairness?.channel
  const f = (check as unknown as { features?: Record<string, number> })?.features
  return (
    <div className="max-w-[40rem]">
      <h1 className="text-[34px] font-semibold">Ferot Guard</h1>
      <p className="mt-3 text-[16px] text-ink-2">
        Most wrong sends can be stopped before they happen. Guard checks the number and the receiving wallet while the customer is
        still on the confirm screen, and explains any warning in plain Bangla. It never blocks a transfer.
      </p>
      <ol className="mt-6 space-y-3 text-[15px]">
        <li className="grid grid-cols-[1.75rem_1fr]"><span className="num text-turmeric font-semibold">1</span><span><b>Rahim's usual transfer</b> to his brother goes straight through, with no warning.</span></li>
        <li className="grid grid-cols-[1.75rem_1fr]"><span className="num text-turmeric font-semibold">2</span><span><b>The transfer that went wrong</b> swaps two digits of that number. Guard asks “Did you mean…?” and offers the right one.</span></li>
        <li className="grid grid-cols-[1.75rem_1fr]"><span className="num text-turmeric font-semibold">3</span><span><b>Shirin</b> is about to “return” money to a caller's number that 14 other people reported. Guard shows why and adds a 30-second pause.</span></li>
      </ol>

      <section className="mt-8 rounded-xl border border-line bg-surface p-5" aria-live="polite">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-[17px] font-semibold">What Guard saw</h2>
          <span className="text-[12.5px] text-ink-3">Shown for the demo. The customer only sees the plain warning.</span>
        </div>
        {check ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
              <div><div className="text-[13px] text-ink-3">Risk</div><div className="num text-[34px] font-semibold leading-none">{check.risk}</div></div>
              <div><div className="text-[13px] text-ink-3">Result</div><div className={`text-[18px] font-semibold ${check.band === 'review' ? 'text-signal' : check.band === 'warn' ? 'text-turmeric-ink' : 'text-flag'}`}>{{ allow: 'Allowed', warn: 'Warned', review: 'Warned with a pause' }[check.band]}</div></div>
              <div><div className="text-[13px] text-ink-3">Scam probability</div><div className="num text-[18px]">{check.p_scam < 0.0001 ? 'under 0.01%' : `${(check.p_scam * 100).toFixed(check.p_scam < 0.01 ? 2 : 0)}%`}</div></div>
              <div><div className="text-[13px] text-ink-3">Check</div><div className="num text-[15px] text-ink-2">{check.check_id}</div></div>
            </div>
            <Gauge risk={check.risk} />
            {check.typo && check.risk < 30 && (
              <p className="text-[14px] text-ink-2">The scam risk is low, but the number is one keypad slip from {check.typo.candidate}, which this customer has paid {check.typo.count} times. The typo check warns on its own.</p>
            )}
            {f && (
              <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5 text-[14px]">
                {FEATURE_TEXT.map(([k, label, fmt]) => f[k] !== undefined && (
                  <div key={k} className="flex justify-between gap-3 border-b border-line-2 py-1">
                    <dt className="text-ink-2">{label}</dt><dd className="num">{fmt(Number(f[k]))}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        ) : <p className="mt-3 text-[14.5px] text-ink-3">Pick a customer and press Next to run a check.</p>}
      </section>

      {g && (
        <section className="mt-8">
          <h2 className="text-[17px] font-semibold">How often it is right (held-out test transfers)</h2>
          <dl className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-6">
            <div><dt className="text-[13px] text-ink-3">Scam sends warned</dt><dd className="num text-[26px] font-semibold">{(g.recall_at_warn * 100).toFixed(1)}%</dd></div>
            <div><dt className="text-[13px] text-ink-3">Warnings that were scams</dt><dd className="num text-[26px] font-semibold">{(g.precision_at_warn * 100).toFixed(0)}%</dd></div>
            <div><dt className="text-[13px] text-ink-3">Typos caught</dt><dd className="num text-[26px] font-semibold">{(g.typo_caught_rate * 100).toFixed(0)}%</dd></div>
            <div><dt className="text-[13px] text-ink-3">Ordinary sends interrupted</dt><dd className="num text-[26px] font-semibold">{g.innocent_warned_per_100}<span className="text-[15px] font-normal text-ink-3"> in 100</span></dd></div>
          </dl>
          {fair && (
            <p className="mt-3 text-[14px] text-ink-2">
              Fairness check: USSD users are interrupted {fair.ussd.innocent_warned_per_100} times per 100 ordinary sends, app users{' '}
              {fair.app.innocent_warned_per_100}. Both are low, but the gap is reported and watched.
            </p>
          )}
          <p className="mt-2 text-[13px] text-ink-3">
            {g.test_scams} scam transfers among {g.test_transfers.toLocaleString('en-US')} test transfers, synthetic data. The scam pattern is cleaner than real fraud,
            so expect lower numbers on upay's data. On USSD the same check would run as one extra confirm screen.
          </p>
        </section>
      )}
    </div>
  )
}

function ReportSide({ go, done }: { go: (to: string) => void; done: boolean }) {
  const items: [string, string][] = [
    ['Consent and notice first', 'Purpose, retention, who sees it and how to withdraw, before anything is processed (PDPO 2025).'],
    ['Responsibilities stated plainly', "upay's terms make the sender responsible for the number; a return needs the recipient's consent or legal process. No refund is promised."],
    ['A real deadline', '10 working days, Sunday to Thursday, skipping public holidays (MFS Regulations 2022, §17.3).'],
    ['Where to escalate', "Bangladesh Bank's complaint channel is named on every status screen (§17.4)."],
    ['A human review on request', 'The customer can contest any outcome and a person looks at it again.'],
  ]
  return (
    <div className="max-w-[40rem]">
      <h1 className="text-[34px] font-semibold">Reporting a wrong send</h1>
      <p className="mt-3 text-[16px] text-ink-2">
        The customer picks the transaction from their history, which removes most reading errors, then writes a few words in
        any language. Ferot builds the case file before an agent opens it.
      </p>
      <dl className="mt-6 space-y-4">
        {items.map(([k, v]) => (
          <div key={k} className="border-l-2 border-flag pl-4">
            <dt className="font-semibold">{k}</dt>
            <dd className="text-[14.5px] text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
      <div className={`mt-8 rounded-xl p-5 ${done ? 'bg-flag-soft' : 'bg-paper-2'}`}>
        <p className="text-[15px]">{done ? 'The case is in the agent queue now, with its evidence already gathered.' : 'After you submit, the case appears at the top of the agent queue.'}</p>
        <Button className="mt-3" tone={done ? 'primary' : 'secondary'} onClick={() => go('/console')}>Open the agent console</Button>
      </div>
    </div>
  )
}
