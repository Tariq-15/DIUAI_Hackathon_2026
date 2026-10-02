# Planted demo scenarios (test window, unseen by training)

| ID | Scenario | Expected | Actual | Score | Pass |
|---|---|---|---|---|---|
| SC-01 | SIM-swap takeover of a business owner at 01:40 | HOLD | HOLD | 100.0 | yes |
| SC-02 | Agent-register harvest: OTP takeover drains 12,500 to 4 mules in 30 s | STEP_UP | HOLD | 100.0 | yes |
| SC-03 | Collector wallet: 2 days old, 14 strangers paid it in 3 h; victim #15 about to send | STEP_UP | HOLD | 100.0 | yes |
| SC-04 | Mule chain through a 400-day-old dormant account (hops of 4, 6, 9 min) | STEP_UP | HOLD | 98.0 | yes |
| SC-05 | 'Jail guard' pressure scam: 60+ USSD farmer cashes in 20,000 and sends it | NUDGE | NUDGE | 30.5 | yes |
| SC-06 | Rogue agent: night cash-outs for the ring, ~8-10x peer volume | FLAGGED | FLAGGED | 85.8 | yes |
| SC-07 | Stolen card: 2 x 25,000 Add Money at 03:10, cash-out 29,500 at 03:40 | HOLD | HOLD | 100.0 | yes |
| SC-08 | Fake phone seller: 9 advance payments in 3 days; buyer #1 already reported it to 16268 | NUDGE | HOLD | 88.6 | yes |
| SB-01 | Busy shop owner's personal wallet: 12 payers in a day | ALLOW | ALLOW | 10.6 | yes |
| SB-02 | Legit new phone, then usual bill + 2,000 to mother | ALLOW | ALLOW | 15.3 | yes |
| SB-03 | Rent advance: 35,000 to a new landlord, Friday 11:00, own phone | NUDGE | STEP_UP (established parties cap) | 98.6 | yes |
| SB-04 | Student cashes out 4,900 twelve minutes after parent sends 5,000 | ALLOW | ALLOW | 0.2 | yes |
| SB-05 | Remittance family cashes out 29,500 twenty minutes after 48,250 lands | ALLOW | ALLOW | 2.4 | yes |

## SC-01: SIM-swap takeover of a business owner at 01:40
- txn `T00608619` (SEND_MONEY), band **HOLD**, score 100.0 (p_fraud 0.9999, anomaly 1.0, graph 0.0)
- A phone first seen on this account 0.1 hour(s) ago is being used  
  এই অ্যাকাউন্টে মাত্র ০.১ ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে
- The phone involved is used by 7 different wallets  
  সংশ্লিষ্ট ফোনটি ৭টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে
- A wallet silent for 44 days suddenly became active  
  ৪৪ দিন নিষ্ক্রিয় থাকা ওয়ালেট হঠাৎ সক্রিয়
- Very unusual for this customer's own past behaviour (top 2% anomaly)  
  এই গ্রাহকের নিজের আগের আচরণের তুলনায় অত্যন্ত অস্বাভাবিক
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। এই অ্যাকাউন্টে মাত্র ০.১ ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে। সংশ্লিষ্ট ফোনটি ৭টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. A phone first seen on this account 0.1 hour(s) ago is being used. The phone involved is used by 7 different wallets. Call 16268 if you need help.)

## SC-02: Agent-register harvest: OTP takeover drains 12,500 to 4 mules in 30 s
- txn `T00605671` (SEND_MONEY), band **HOLD**, score 100.0 (p_fraud 0.9995, anomaly 0.953, graph 0.018)
- A phone first seen on this account 0.0 hour(s) ago is being used  
  এই অ্যাকাউন্টে মাত্র ০.০ ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে
- Recipient wallet was opened only 3 day(s) ago  
  এই নম্বরটি মাত্র ৩ দিন আগে খোলা হয়েছে
- You have never sent money to this number before  
  এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। এই অ্যাকাউন্টে মাত্র ০.০ ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে। এই নম্বরটি মাত্র ৩ দিন আগে খোলা হয়েছে। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. A phone first seen on this account 0.0 hour(s) ago is being used. Recipient wallet was opened only 3 day(s) ago. Call 16268 if you need help.)

## SC-03: Collector wallet: 2 days old, 14 strangers paid it in 3 h; victim #15 about to send
- txn `T00641926` (SEND_MONEY), band **HOLD**, score 100.0 (p_fraud 0.9995, anomaly 0.85, graph 0.995)
- 14 different people sent money to this number in the last 24 hours  
  গত ২৪ ঘণ্টায় ১৪ জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন
- Recipient wallet was opened only 2 day(s) ago  
  এই নম্বরটি মাত্র ২ দিন আগে খোলা হয়েছে
- Unusual time for this customer (12:00)  
  আপনার জন্য অস্বাভাবিক সময় (১২:০০)
- Part of a suspicious money-movement network (graph rules)  
  সন্দেহজনক টাকা লেনদেন নেটওয়ার্কের অংশ
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। গত ২৪ ঘণ্টায় ১৪ জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন। এই নম্বরটি মাত্র ২ দিন আগে খোলা হয়েছে। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. 14 different people sent money to this number in the last 24 hours. Recipient wallet was opened only 2 day(s) ago. Call 16268 if you need help.)

## SC-04: Mule chain through a 400-day-old dormant account (hops of 4, 6, 9 min)
- txn `T00633394` (SEND_MONEY), band **HOLD**, score 98.0 (p_fraud 0.9049, anomaly 0.998, graph 0.3)
- Recipient wallet was opened only 6 day(s) ago  
  এই নম্বরটি মাত্র ৬ দিন আগে খোলা হয়েছে
- Tk 19,500 is 1.0x the largest amount this customer has sent  
  ৳১৯,৫০০ আপনার আগের সর্বোচ্চ লেনদেনের ১.০ গুণ
- You have never sent money to this number before  
  এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি
- Very unusual for this customer's own past behaviour (top 2% anomaly)  
  এই গ্রাহকের নিজের আগের আচরণের তুলনায় অত্যন্ত অস্বাভাবিক
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। এই নম্বরটি মাত্র ৬ দিন আগে খোলা হয়েছে। ৳১৯,৫০০ আপনার আগের সর্বোচ্চ লেনদেনের ১.০ গুণ। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. Recipient wallet was opened only 6 day(s) ago. Tk 19,500 is 1.0x the largest amount this customer has sent. Call 16268 if you need help.)

## SC-05: 'Jail guard' pressure scam: 60+ USSD farmer cashes in 20,000 and sends it
- txn `T00590040` (SEND_MONEY), band **NUDGE**, score 30.5 (p_fraud 0.0007, anomaly 0.871, graph 0.3)
- This moves 94% of the balance  
  আপনার ব্যালেন্সের ৯৪% পাঠানো হচ্ছে
- Tk 20,000 is 7.4x the largest amount this customer has sent  
  ৳২০,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ৭.৪ গুণ
- You have never sent money to this number before  
  এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি
- Customer sees: সতর্কতা: আপনার ব্যালেন্সের ৯৪% পাঠানো হচ্ছে। ৳২০,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ৭.৪ গুণ। আপনি কি এই ব্যক্তিকে ব্যক্তিগতভাবে চেনেন?
  (Caution: This moves 94% of the balance. Tk 20,000 is 7.4x the largest amount this customer has sent. Do you personally know this person?)

## SC-07: Stolen card: 2 x 25,000 Add Money at 03:10, cash-out 29,500 at 03:40
- txn `T00629693` (CASH_OUT), band **HOLD**, score 100.0 (p_fraud 0.9998, anomaly 0.998, graph 0.3)
- The phone involved is used by 11 different wallets  
  সংশ্লিষ্ট ফোনটি ১১টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে
- The sending wallet itself is only 4 day(s) old  
  প্রেরক ওয়ালেটটি মাত্র ৪ দিন পুরনো
- Money that arrived 26 minute(s) ago is being moved straight on  
  ২৬ মিনিট আগে আসা টাকা সাথে সাথে অন্যত্র সরানো হচ্ছে
- Very unusual for this customer's own past behaviour (top 2% anomaly)  
  এই গ্রাহকের নিজের আগের আচরণের তুলনায় অত্যন্ত অস্বাভাবিক
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। সংশ্লিষ্ট ফোনটি ১১টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে। প্রেরক ওয়ালেটটি মাত্র ৪ দিন পুরনো। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. The phone involved is used by 11 different wallets. The sending wallet itself is only 4 day(s) old. Call 16268 if you need help.)

## SC-08: Fake phone seller: 9 advance payments in 3 days; buyer #1 already reported it to 16268
- txn `T00616551` (SEND_MONEY), band **HOLD**, score 88.6 (p_fraud 0.4655, anomaly 0.326, graph 0.6)
- Other customers have reported this number (or wallets it trades with) to 16268  
  অন্য গ্রাহকরা এই নম্বর বা এর সাথে লেনদেনকারী ওয়ালেটের বিরুদ্ধে ১৬২৬৮-এ অভিযোগ করেছেন
- Tk 6,000 is 1.0x the largest amount this customer has sent  
  ৳৬,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ১.০ গুণ
- You have never sent money to this number before  
  এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি
- Part of a suspicious money-movement network (graph rules)  
  সন্দেহজনক টাকা লেনদেন নেটওয়ার্কের অংশ
- Customer sees: আপনার নিরাপত্তার জন্য লেনদেনটি সাময়িকভাবে স্থগিত রাখা হয়েছে। অন্য গ্রাহকরা এই নম্বর বা এর সাথে লেনদেনকারী ওয়ালেটের বিরুদ্ধে ১৬২৬৮-এ অভিযোগ করেছেন। ৳৬,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ১.০ গুণ। প্রয়োজনে ১৬২৬৮ নম্বরে কল করুন।
  (We have paused this transaction for your safety. Other customers have reported this number (or wallets it trades with) to 16268. Tk 6,000 is 1.0x the largest amount this customer has sent. Call 16268 if you need help.)

## SB-01: Busy shop owner's personal wallet: 12 payers in a day
- txn `T00625205` (SEND_MONEY), band **ALLOW**, score 10.6 (p_fraud 0.0002, anomaly 0.874, graph 0.0)
- 13 different people sent money to this number in the last 24 hours  
  গত ২৪ ঘণ্টায় ১৩ জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন

## SB-02: Legit new phone, then usual bill + 2,000 to mother
- txn `T00605254` (SEND_MONEY), band **ALLOW**, score 15.3 (p_fraud 0.0003, anomaly 0.663, graph 0.5)
- A phone first seen on this account 0.3 hour(s) ago is being used  
  এই অ্যাকাউন্টে মাত্র ০.৩ ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে
- The phone involved is used by 4 different wallets  
  সংশ্লিষ্ট ফোনটি ৪টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে
- Part of a suspicious money-movement network (graph rules)  
  সন্দেহজনক টাকা লেনদেন নেটওয়ার্কের অংশ

## SB-03: Rent advance: 35,000 to a new landlord, Friday 11:00, own phone
- txn `T00588181` (SEND_MONEY), band **STEP_UP**, score 98.6 (p_fraud 0.9323, anomaly 0.997, graph 0.0)
- Tk 35,000 is 3.7x the largest amount this customer has sent  
  ৳৩৫,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ৩.৭ গুণ
- You have never sent money to this number before  
  এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি
- This moves 74% of the balance  
  আপনার ব্যালেন্সের ৭৪% পাঠানো হচ্ছে
- Very unusual for this customer's own past behaviour (top 2% anomaly)  
  এই গ্রাহকের নিজের আগের আচরণের তুলনায় অত্যন্ত অস্বাভাবিক
- Customer sees: নিশ্চিত করতে আবার পিন দিন। ৳৩৫,০০০ আপনার আগের সর্বোচ্চ লেনদেনের ৩.৭ গুণ। এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি। upay কখনো ফোনে পিন বা ওটিপি চায় না।
  (Please confirm with your PIN. Tk 35,000 is 3.7x the largest amount this customer has sent. You have never sent money to this number before. upay never asks for your PIN or OTP on a call.)

## SB-04: Student cashes out 4,900 twelve minutes after parent sends 5,000
- txn `T00609423` (CASH_OUT), band **ALLOW**, score 0.2 (p_fraud 0.0, anomaly 0.825, graph 0.3)
- Tk 4,900 is 3.2x the largest amount this customer has sent  
  ৳৪,৯০০ আপনার আগের সর্বোচ্চ লেনদেনের ৩.২ গুণ
- Unusual time for this customer (10:00)  
  আপনার জন্য অস্বাভাবিক সময় (১০:০০)
- Money that arrived 12 minute(s) ago is being moved straight on  
  ১২ মিনিট আগে আসা টাকা সাথে সাথে অন্যত্র সরানো হচ্ছে

## SB-05: Remittance family cashes out 29,500 twenty minutes after 48,250 lands
- txn `T00633934` (CASH_OUT), band **ALLOW**, score 2.4 (p_fraud 0.0, anomaly 0.928, graph 0.3)
- Money that arrived 20 minute(s) ago is being moved straight on  
  ২০ মিনিট আগে আসা টাকা সাথে সাথে অন্যত্র সরানো হচ্ছে
- Tk 29,500 is 1.7x the largest amount this customer has sent  
  ৳২৯,৫০০ আপনার আগের সর্বোচ্চ লেনদেনের ১.৭ গুণ
- Unusual time for this customer (16:00)  
  আপনার জন্য অস্বাভাবিক সময় (১৬:০০)
