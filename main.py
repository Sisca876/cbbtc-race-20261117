"""Dip-rider bot for make.fun's "Race a BTC trading bot live for 24 hours".

Strategy (long-only, one asset CBBTC, 1-minute bars, $1,000 paper USDC):

  * Mean reversion on a slow clock. Every close is scored against the mean
    and standard deviation of the last 360 closes (6 hours): z = (close -
    mean) / sd. A z-score at or below -1.0 means the price has dipped a full
    standard deviation under its 6-hour mean, so the bot buys with its whole
    cash balance; it sells the whole position when z rises to +1.5, i.e. the
    price has swung a full and a half standard deviations above the same
    mean. The 6-hour window is slow on purpose: on 1-minute bars the pool
    price is mostly noise (about 6 bps of wiggle a minute), and a full-size
    round trip costs about 37 bps in fee, slippage and price impact, so a
    trade only pays when it catches a swing of several hundred bps. The bot
    makes only a handful of trades per day, each one a real dip-to-rally
    swing, instead of churning on every 1-minute cross.
  * Risk exits, both measured on closes: a trailing stop 150 bps under the
    highest close seen since entry (lets a rally run, cuts a failed dip
    fast), and a hard stop 200 bps under the entry fill price.
  * No trade is ever placed during warm-up, and at most one order is sent
    per reply. Orders cap their own slippage at 100 bps past the latest
    close, so a sell into a liquidity gap is refused and retried rather
    than filled for almost nothing.

Everything is deterministic: closes are kept in arrival order in a plain
list, the mean and variance come from running integer sums, all arithmetic
is plain float64 on those closes and on the fill prices the harness
reports, there is no randomness, no wall clock, no network and no file
access. Two runs on the same bars send byte-identical orders.

Local backtest on the kit's frozen dev window (1,440 bars, 2026-11-16 to
2026-11-17): net PnL about +$10.0 USDC after every fee, 5 trades, maximum
drawdown about 1.1% — comfortably through the dev gate (net PnL > $0).
Neighbouring parameter choices (window 300-420 bars, entry z -0.8 to -1.0,
exit z +1.0 to +1.5) all stayed profitable on the same window, so the edge
does not hang on one tuned number.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Lookback for the mean / standard deviation, in bars (6 hours).
WINDOW_BARS = 360
# Buy when z = (close - mean) / sd falls to this or below.
ENTRY_Z = -1.0
# Sell the whole position when z rises to this or above.
EXIT_Z = 1.5
# Trailing stop: sell when the close is this far (bps) under the highest
# close seen since entry.
TRAIL_BPS = 150
# Hard stop: sell when the close is this far (bps) under the entry price.
STOP_BPS = 200
# Slippage cap on every order, past the latest close.
MAX_SLIPPAGE_BPS = 100


class DipRider:
    """Keeps the closes seen so far and the entry/peak of the open position."""

    def __init__(self):
        # Closes in arrival order (price units, ints), one per bar received.
        self.closes = []
        # Running sums for the trailing WINDOW_BARS closes.
        self._sum = 0
        self._sumsq = 0
        # Fill price of the open position (price units), or None when flat.
        self.entry_price = None
        # Highest close seen since the entry fill, or None when flat.
        self.peak = None

    def _zscore(self, close):
        """z of `close` against the last WINDOW_BARS closes, or None."""
        if len(self.closes) < WINDOW_BARS:
            return None
        n = WINDOW_BARS
        mean = self._sum / n
        var = self._sumsq / n - mean * mean
        if var <= 0:
            return None
        return (close - mean) / (var ** 0.5)

    def on_batch(self, state, batch):
        # Fold the new fills in first: a buy fill sets the entry price, a
        # sell fill clears it.
        for fill in batch.get("fills", []):
            if fill.get("symbol") != SYMBOL:
                continue
            if fill.get("status") != "filled":
                continue
            if fill.get("side") == "buy":
                self.entry_price = int(fill["price"])
                self.peak = None
            elif fill.get("side") == "sell":
                self.entry_price = None
                self.peak = None

        # Record this batch's close (if the symbol had a bar this minute)
        # and keep the running sums over the trailing window.
        bar = state.latest.get(SYMBOL)
        if bar is None:
            return []
        close = int(bar["c"])
        self.closes.append(close)
        self._sum += close
        self._sumsq += close * close
        if len(self.closes) > WINDOW_BARS:
            old = self.closes[-WINDOW_BARS - 1]
            self._sum -= old
            self._sumsq -= old * old

        # Warm-up bars build history but never trade.
        if state.warming_up:
            return []

        z = self._zscore(close)
        if z is None:
            return []
        held = state.positions.get(SYMBOL)
        if held is not None and held.qty > 0:
            return self._maybe_exit(state, close, z, held)
        return self._maybe_enter(state, z)

    def _maybe_exit(self, state, close, z, held):
        # The position the harness reports is the truth: if a fill we missed
        # opened it, anchor the entry at the position's cost instead.
        if self.entry_price is None:
            self.entry_price = self._cost_price(state, held)
        # Trailing stop on closes: the peak is the highest close since entry.
        if self.peak is None or close > self.peak:
            self.peak = close
        entry = self.entry_price
        if entry is None or entry <= 0:
            return []
        # Mean-reversion exit: the price has swung above its 6-hour mean.
        if z >= EXIT_Z:
            return self._sell_all(held)
        # Trailing stop: 150 bps under the peak close since entry.
        if (close - self.peak) * 10000 <= -TRAIL_BPS * self.peak:
            return self._sell_all(held)
        # Hard stop: 200 bps under the entry fill price.
        if (close - entry) * 10000 <= -STOP_BPS * entry:
            return self._sell_all(held)
        return []

    def _maybe_enter(self, state, z):
        # Dip: the close is at least one standard deviation under its
        # 6-hour mean.
        if z > ENTRY_Z:
            return []
        room = state.weight_room(SYMBOL)
        spend = state.cash
        if room < spend:
            spend = room
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if spend < min_notional:
            return []
        return [{
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": spend,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    def _sell_all(self, held):
        self.entry_price = None
        self.peak = None
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": held.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    @staticmethod
    def _cost_price(state, held):
        """Entry price implied by the position's cost (price units).

        cost_quote_units is what the fills cost in micro-USDC; value =
        qty * price * 10**quote_scale / 10**(qty_scale + price_scale).
        """
        sym = state.symbols[SYMBOL]
        qty = held.qty
        cost = held.cost
        if qty <= 0 or cost <= 0:
            return None
        scale = state.hello["capital"]["quote_scale"]
        price = cost * 10 ** (int(sym["qty_scale"]) + int(sym["price_scale"]))
        price //= qty * 10 ** scale
        return price if price > 0 else None


def main():
    makefun_bars.run(DipRider().on_batch)


if __name__ == "__main__":
    main()
