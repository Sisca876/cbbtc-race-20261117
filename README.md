# cbbtc-race-20261117

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/Sisca876/cbbtc-race-20261117/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/Sisca876/cbbtc-race-20261117/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A mean-reversion trading bot for cbBTC (Coinbase Wrapped BTC) on Solana, built for make.fun's "Race a BTC trading bot live for 24 hours" bounty. It trades 1-minute on-chain bars from the Orca Whirlpool with $1,000 of paper money: it buys when the price dips at least one standard deviation under its 6-hour mean and sells when it swings 1.5 standard deviations above it, with a 150 bps trailing stop and a 200 bps hard stop. Deterministic, standard library only, no network and no wall clock.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout: the harness sends `hello`, one `batch` per minute bar, then `done`, and the bot answers each batch with one `reply` carrying its orders.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
