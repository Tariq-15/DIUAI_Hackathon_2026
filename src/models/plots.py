"""Static report figures (PNG) in one consistent style.

Palette = the validated default categorical order (fixed slots, never cycled); policy bands
use the reserved status colours and always carry a text label. Thin lines, recessive grid,
one y-axis per chart, a legend whenever there are >= 2 series.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE_ORDINAL = ["#86b6ef", "#2a78d6", "#104281"]           # sequential blue, steps 250 / 450 / 650
STATUS = {"ALLOW": "#0ca30c", "NUDGE": "#fab219", "STEP_UP": "#ec835a", "HOLD": "#d03b3b"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titlesize": 12,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 10,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
        "legend.fontsize": 9, "legend.labelcolor": INK2, "lines.linewidth": 2.0,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    })


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def pr_curves(curves: dict, path: Path, title="Precision-recall on the test window"):
    """curves: name -> (precision, recall, pr_auc). <= 5 series, fixed slot order."""
    style()
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for i, (name, (p, r, a)) in enumerate(curves.items()):
        ax.plot(r, p, color=SERIES[i], label=f"{name} (PR-AUC {a:.3f})", linewidth=2.0)
    ax.set_xlabel("Recall (share of fraud caught)")
    ax.set_ylabel("Precision (share of alerts that are fraud)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_title(title)
    ax.legend(loc="lower left")
    return _save(fig, path)


def score_hist(score, y, cuts: dict, path: Path):
    style()
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    bins = np.linspace(0, 100, 51)
    ax.hist(score[y == 0], bins=bins, color=SERIES[0], alpha=0.85, label="legit", rwidth=0.9)
    ax.hist(score[y == 1], bins=bins, color=SERIES[1], alpha=0.9, label="fraud", rwidth=0.9)
    ax.set_yscale("log")
    for name, x in cuts.items():
        ax.axvline(x, color=AXIS, linewidth=1)
        ax.text(x + 1, ax.get_ylim()[1] * 0.5, name, color=INK2, fontsize=8, rotation=90, va="top")
    ax.set_xlabel("Risk score (0-100)")
    ax.set_ylabel("Transactions (log scale)")
    ax.set_title("Risk score distribution, test window")
    ax.legend(loc="upper center")
    return _save(fig, path)


def scenario_recall(df, path: Path):
    """df: scenario, recall_nudge, recall_stepup, recall_hold (ordinal levels -> one-hue ramp)."""
    style()
    fig, ax = plt.subplots(figsize=(6.4, 0.5 * len(df) + 1.6))
    y = np.arange(len(df))
    h = 0.26
    for j, (col, lab) in enumerate((("recall_nudge", "NUDGE or higher"), ("recall_stepup", "STEP_UP or higher"),
                                    ("recall_hold", "HOLD"))):
        ax.barh(y + (1 - j) * h, df[col], height=h - 0.03, color=BLUE_ORDINAL[j], label=lab)
    for i, v in enumerate(df["recall_stepup"]):
        ax.text(v + 0.012, i, f"{v:.0%}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, df["label"])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.1)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("Share of fraud transactions flagged (label = STEP_UP or higher)")
    ax.set_title("Recall by scam type, test window")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=3, fontsize=8)
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def hbar(values: dict, path: Path, title: str, xlabel: str, ref=None, ref_label=None, fmt="{:.3f}"):
    style()
    names = list(values)
    vals = np.array([values[k] for k in names], float)
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(names) + 1.4))
    y = np.arange(len(names))
    ax.barh(y, vals, color=SERIES[0], height=0.62)
    for i, v in enumerate(vals):
        ax.text(v, i, " " + fmt.format(v), va="center", fontsize=8, color=INK2)
    if ref is not None:
        ax.axvline(ref, color=INK2, linewidth=1, linestyle="--")
        ax.text(ref, len(names) - 0.4, f" {ref_label}", fontsize=8, color=INK2)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    if "%" in fmt:
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def agent_volume(days, me, peer, episodes, path: Path, agent_id: str):
    style()
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for s, e in episodes:
        ax.axvspan(s - 0.5, e + 0.5, color=GRID, alpha=0.7, linewidth=0)
    ax.plot(days, peer, color=SERIES[0], label="peer median (same area)")
    ax.plot(days, me, color=SERIES[1], label=agent_id)
    ax.set_xlabel("Day of simulation (shaded = known rogue episode)")
    ax.set_ylabel("Cash-out volume per day")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"Tk {v / 1000:.0f}k"))
    ax.set_title(f"Agent Watch: {agent_id} vs peers")
    ax.legend(loc="upper left")
    return _save(fig, path)
