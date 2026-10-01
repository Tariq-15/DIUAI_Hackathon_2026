"""Fast, read-only lookups over the ledger: balances at a moment, a wallet's transactions in a window.

Every lookup takes an `as_of` minute so features never see the future (no leakage).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ferot import config
from ferot.datagen.generator import World


class Ledger:
    def __init__(self, world: World):
        self.world = world
        tx = world.transactions.reset_index(drop=True)
        self.tx = tx
        self.start = world.start
        self.wallets = world.wallets.set_index("wallet_no")
        self.minute = tx["minute"].to_numpy()
        self.amount = tx["amount"].to_numpy()
        self.type = tx["type"].to_numpy()
        self.sender = tx["sender"].to_numpy()
        self.receiver = tx["receiver"].to_numpy()
        self.status = tx["status"].to_numpy()
        self.out_idx = {k: np.asarray(v) for k, v in tx.groupby("sender").indices.items()}
        self.in_idx = {k: np.asarray(v) for k, v in tx.groupby("receiver").indices.items()}
        self.by_trx = dict(zip(tx["trx_id"], range(len(tx))))

        s = pd.DataFrame({"w": tx["sender"], "m": tx["minute"], "b": tx["sender_balance_after"], "i": tx.index})
        r = pd.DataFrame({"w": tx["receiver"], "m": tx["minute"], "b": tx["receiver_balance_after"], "i": tx.index})
        ev = pd.concat([s, r]).dropna(subset=["b"]).sort_values(["w", "i"], kind="stable")
        self.timeline = {w: (g["m"].to_numpy(), g["b"].to_numpy()) for w, g in ev.groupby("w")}
        self.initial = dict(zip(world.wallets["wallet_no"], world.wallets["initial_balance"]))
        events = world.system_events
        self.failed_trx = set(events.loc[events["event"] == "credit_fail", "trx_id"].dropna())

    # ----- basic lookups -----
    def row(self, trx_id: str) -> pd.Series:
        return self.tx.iloc[self.by_trx[trx_id]]

    def balance_at(self, wallet: str, minute: int) -> float:
        tl = self.timeline.get(wallet)
        if tl is None:
            return float(self.initial.get(wallet, 0.0))
        mins, bals = tl
        k = int(np.searchsorted(mins, minute, side="right")) - 1
        return float(bals[k]) if k >= 0 else float(self.initial.get(wallet, 0.0))

    def _window(self, idx: np.ndarray | None, lo: int, hi: int) -> np.ndarray:
        if idx is None or len(idx) == 0:
            return np.empty(0, dtype=int)
        m = self.minute[idx]
        return idx[(m >= lo) & (m <= hi)]

    def outgoing(self, wallet: str, lo: int, hi: int) -> np.ndarray:
        return self._window(self.out_idx.get(wallet), lo, hi)

    def incoming(self, wallet: str, lo: int, hi: int) -> np.ndarray:
        return self._window(self.in_idx.get(wallet), lo, hi)

    def wallet_info(self, wallet: str) -> dict:
        if wallet not in self.wallets.index:
            return {}
        w = self.wallets.loc[wallet]
        return {"kyc_level": w["kyc_level"], "district": w["district"], "channel": w["channel"],
                "age_band": w["age_band"], "language": w["language"], "opened_minute": int(w["opened_minute"])}

    def owner_type(self, wallet: str) -> str:
        """Used only for display (agent / merchant names in the money trail), never as a model feature."""
        return str(self.wallets.loc[wallet, "owner_type"]) if wallet in self.wallets.index else "unknown"

    def ts(self, minute: int) -> str:
        return (self.start + pd.Timedelta(minutes=int(minute))).isoformat()


@lru_cache
def load_ledger() -> Ledger:
    return Ledger(World.load(config.settings().data_dir))
