# Trade Performance Audit - results

Statement period: 24 Jun 2026 to 06 Oct 2026  
Closed deals analysed: 120

## Core numbers

| Metric | Value |
|---|---|
| Net P&L | +$231.96 |
| Winning / losing / breakeven deals | 59 / 59 / 2 |
| Win rate (all deals) | 49.2% |
| Win rate (excluding breakeven) | 50.0% |
| Average win | +$7.75 |
| Average loss | −$3.82 |
| Payoff ratio (average win / average loss) | 2.03 |
| Profit factor (gross profit / gross loss) | 2.03 |
| Expectancy per deal | +$1.93 |
| Median deal | $0.00 |
| Best / worst deal | +$137.95 / −$24.58 |
| Max drawdown on cumulative P&L | $79.19 |
| Longest losing streak (deals) | 7 |

## Does the edge survive without the best deals?

| Removed | Their P&L | Net P&L without them | Share of total net |
|---|---|---|---|
| best 1 | +$137.95 | +$94.01 | 59% |
| best 3 | +$289.93 | −$57.97 | 125% |
| best 5 | +$338.43 | −$106.47 | 146% |

## Bootstrap: is the average deal really positive?

Resampled the 120 deals 10,000 times. Average P&L per deal: +$1.93. 95% range: −$0.70 to +$5.36. In 10.1% of resamples the average was zero or negative.

The 95% range includes zero, so this sample cannot rule out that the true average is zero. More trades are needed.

## By asset class

| Asset class | Deals | Net P&L | Win rate | Average deal |
|---|---|---|---|---|
| Indices | 36 | +$160.81 | 44% | +$4.47 |
| Metals | 17 | +$102.38 | 71% | +$6.02 |
| FX | 38 | +$6.60 | 42% | +$0.17 |
| Crypto | 29 | −$37.83 | 52% | −$1.30 |

## Balance changes not explained by deal P&L

13 balance changes of 5 USD or more are not explained by closed-deal P&L (likely deposits, withdrawals, transfers or fees). Because of these, a percentage return cannot be computed from this file alone.

## Limits of this analysis

- The statement shows closing times only. It has no opening time and no stop-loss, so holding periods and risk per trade (R-multiples) cannot be measured here.
- A position closed in parts appears as several deals, so counts and win rate are per deal, not per trade.
- The sample is small, and deals are not fully independent (several can come from one idea).
- Max drawdown here is in dollars on cumulative P&L, not a percentage of account equity.
