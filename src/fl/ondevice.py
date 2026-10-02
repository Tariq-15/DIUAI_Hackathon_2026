"""On-device federated learning for the wrong-person check: which finger slips are common?

    python -m src.fl.ondevice        # -> artifacts/portable/slip_costs.json, reports/federated_ondevice.json

Each phone keeps its own contact list and its own typing slips. When a customer taps "use the suggested number",
the phone learns one confirmed slip: which digit was meant and which was typed (or two digits swapped). Phones
never send those events. Each phone sends only a noisy count matrix, and the server only sees sums over groups of
phones (secure aggregation: pairwise masks that cancel, modular arithmetic). From the sum it estimates how likely
each slip is and turns that into the edit costs src/serve/recipient.py uses.

Two noise settings are run and reported side by side:
  distributed (used): each phone adds 1/m of the Gaussian noise, so every group sum the server can see carries the
      full noise and is (epsilon, delta)-differentially private. Trust needed: secure aggregation works and phones
      add their share.
  local (comparison): each phone adds the full noise, so even its own report is private on its own. No trust
      needed, but the sum is far noisier for the same epsilon.

This is a SIMULATION of the protocol: the phones and their slips are synthetic (the slip process follows the
typo model of our Track 06 project: 70% neighbouring key, 30% any other key, plus adjacent swaps). What is real
is the mechanism and the check that the server recovers the slip pattern without seeing a single event.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from src.common.config import ROOT
from src.serve.recipient import DIGITS, KEYPAD_NEIGHBOURS

D = 10
CELLS = D * D + 1                  # 10x10 substitutions (meant -> typed) + 1 adjacent swap
FIXED = 2 ** 20                    # fixed-point scale for secure aggregation (exact integer sums mod 2^64)


def true_slip_model(p_neighbour=0.7, p_swap=0.35) -> np.ndarray:
    """Ground truth used to SIMULATE slips: P(event) over the 101 cells, given that a slip happens."""
    sub = np.zeros((D, D))
    for i, a in enumerate(DIGITS):
        nb = [DIGITS.index(b) for b in KEYPAD_NEIGHBOURS[a]]
        other = [j for j in range(D) if j != i and j not in nb]
        sub[i, nb] = p_neighbour / len(nb)
        sub[i, other] = (1 - p_neighbour) / len(other)
    sub = sub / D * (1 - p_swap)                     # meant digit uniform over the 10 keys
    return np.concatenate([sub.ravel(), [p_swap]])


def phone_counts(rng, n_slips: int, truth: np.ndarray, cap: int) -> np.ndarray:
    """One phone's private data: its confirmed slips (at most `cap` are reported per round)."""
    ev = rng.choice(CELLS, size=min(n_slips, cap), p=truth)
    return np.bincount(ev, minlength=CELLS).astype(float)


def secure_sum(updates: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Masked aggregation of a group of phone reports (rows). Phone i adds mask s_i - s_(i+1) (a seed shared with its
    neighbour in a ring), so every report the server sees looks random, yet the masks cancel exactly in the sum.
    Fixed-point integers modulo 2^64 make the cancellation exact."""
    enc = np.round(updates * FIXED).astype(np.int64).view(np.uint64)
    s = rng.integers(0, 2 ** 63, size=enc.shape, dtype=np.uint64)
    masked = enc + s - np.roll(s, -1, axis=0)                 # uint64 arithmetic wraps modulo 2^64
    total = masked.sum(axis=0, dtype=np.uint64)
    return total.view(np.int64).astype(float) / FIXED, masked


def costs_from(p: np.ndarray, min_rate: float = 0.0) -> dict:
    """Most likely slip for a digit costs 0.6, a slip never seen costs 1.0 (Ferot's scale); adjacent swaps 0.8 if common."""
    sub = p[:-1].reshape(D, D).clip(min=0)
    out = {}
    for i, a in enumerate(DIGITS):
        row = sub[i].copy()
        row[i] = 0
        top = row.max() or 1.0
        out[a] = {b: (0.0 if i == j else round(0.6 + 0.4 * (1 - row[j] / top), 3)) for j, b in enumerate(DIGITS)}
    share_swap = float(p[-1] / max(p.sum(), 1e-12))
    return dict(sub=out, transposition=0.8 if share_swap >= 0.1 else 1.0, swap_share=round(share_swap, 3))


def epsilon(rounds: int, cap: int, sigma: float, delta: float = 1e-5) -> float:
    """Gaussian mechanism composed over the rounds with Renyi DP; one phone changes a report by at most `cap` (L2)."""
    rdp = lambda a: rounds * a * cap ** 2 / (2 * sigma ** 2)                   # noqa: E731
    return float(min(rdp(a) + math.log(1 / delta) / (a - 1) for a in np.linspace(1.01, 256, 5000)))


def run(n_phones=100_000, rounds=6, online=0.5, mean_slips=1.2, cap=2, sigma=6.0, group=1000, seed=7, noise="distributed",
        verbose=True) -> dict:
    rng = np.random.default_rng(seed)
    truth = true_slip_model()
    total = np.zeros(CELLS)
    history, checked = [], False
    for r in range(rounds):
        n = int(n_phones * online)                                         # the phones online this round
        k = np.minimum(rng.poisson(mean_slips, size=n), cap)               # confirmed slips per phone, capped
        events = rng.choice(CELLS, size=int(k.sum()), p=truth)
        owner = np.repeat(np.arange(n), k)
        counts = np.zeros((n, CELLS))
        np.add.at(counts, (owner, events), 1.0)                            # each phone's private counts
        share = sigma / math.sqrt(group) if noise == "distributed" else sigma   # noise each phone adds before sending
        reports = counts + rng.normal(0, share, size=counts.shape)
        agg = np.zeros(CELLS)
        for g in range(0, n, group):
            part, masked = secure_sum(reports[g:g + group], rng)
            if not checked:                                                # the protocol gives exactly the plain sum
                assert np.allclose(part, reports[g:g + group].sum(axis=0), atol=1e-3)
                checked = True
            agg += part
        total += agg
        est = total.clip(min=0) / max(total.clip(min=0).sum(), 1e-12)
        sub_est = est[:-1].reshape(D, D)
        agree = np.mean([np.argmax(sub_est[i] - np.eye(D)[i] * 1e9) in [DIGITS.index(b) for b in KEYPAD_NEIGHBOURS[a]]
                         for i, a in enumerate(DIGITS)])
        l1 = float(np.abs(est - truth).sum())
        history.append(dict(round=r + 1, phones=n, slips_reported=int(k.sum()), l1_error=round(l1, 4),
                            top_slip_is_neighbour=round(float(agree), 2)))
        if verbose:
            print(f"[on-device FL, {noise} noise] round {r + 1}: {n:,} phones, {int(k.sum()):,} slips, L1 error vs true slip pattern "
                  f"{l1:.3f}, most likely slip is a keypad neighbour for {agree:.0%} of digits")
    learned = costs_from(total.clip(min=0))
    delta = 1e-5
    eps_total = epsilon(rounds, cap, sigma, delta)
    result = dict(
        method="federated aggregation of noisy slip counts; secure aggregation (ring masks, mod 2^64); "
               + ("distributed Gaussian noise: each group sum the server sees is differentially private"
                  if noise == "distributed" else "local Gaussian noise: each phone's report is differentially private on its own"),
        noise=noise, simulated=True, phones=n_phones, online_per_round=online, rounds=rounds, cap_events_per_round=cap,
        group_size=group, noise_sigma=sigma, epsilon_total=round(eps_total, 2), delta=delta, history=history,
        final_l1_error=history[-1]["l1_error"], top_slip_is_neighbour=history[-1]["top_slip_is_neighbour"],
        learned_swap_share=learned["swap_share"], true_swap_share=0.35,
        neighbour_cost_mean=round(float(np.mean([learned["sub"][a][b] for a in DIGITS for b in KEYPAD_NEIGHBOURS[a]])), 3),
        other_cost_mean=round(float(np.mean([learned["sub"][a][b] for a in DIGITS for b in DIGITS
                                             if b != a and b not in KEYPAD_NEIGHBOURS[a]])), 3),
    )
    costs = dict(sub=learned["sub"], transposition=learned["transposition"],
                 source=f"federated: {n_phones:,} simulated phones, {rounds} rounds, secure aggregation, "
                        f"epsilon {result['epsilon_total']} (delta 1e-5)")
    return dict(result=result, costs=costs)


def main():
    out = run()
    local = run(noise="local", verbose=False)["result"]           # same epsilon, no trust in aggregation: how much worse?
    out["result"]["local_noise_comparison"] = {k: local[k] for k in ("final_l1_error", "top_slip_is_neighbour",
                                                                    "neighbour_cost_mean", "other_cost_mean",
                                                                    "learned_swap_share", "epsilon_total")}
    art = ROOT / "artifacts" / "portable"
    art.mkdir(parents=True, exist_ok=True)
    (art / "slip_costs.json").write_text(json.dumps(out["costs"], ensure_ascii=False), encoding="utf-8")
    (ROOT / "reports" / "federated_ondevice.json").write_text(json.dumps(out["result"], indent=1), encoding="utf-8")
    r = out["result"]
    print(f"[on-device FL] neighbouring-key slips learned at cost {r['neighbour_cost_mean']}, other digits "
          f"{r['other_cost_mean']}, swaps {r['learned_swap_share']:.0%} of slips; epsilon {r['epsilon_total']} "
          f"(delta 1e-5) over {r['rounds']} rounds; L1 error {r['final_l1_error']} "
          f"(local noise at the same epsilon: {local['final_l1_error']})")
    from .summary import write
    write()


if __name__ == "__main__":
    main()
