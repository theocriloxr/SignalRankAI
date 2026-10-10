Backtest engine. Leakage detection. Multiple-testing correction. Walk-forward validation. Position sizing.  Five years ago that list was a hedge fund job description. Today it's one evening and a language model.  But the tool cuts both ways — it removed the skill barrier without removing the discipline barrier, and now that ideas are free, discipline is the entire edge. Here's how to build both halves.

Review this backtest for the following errors. For each one,

state PRESENT or ABSENT and quote the line.



1\. Look-ahead: is the signal shifted before becoming a position?

2\. Survivorship: does the asset list include delisted tickers?

3\. Repainting: does any indicator use future data (centered

   moving averages, zigzag, unshifted resample)?

4\. Costs: are fees AND slippage applied on turnover?

5\. Fill assumption: does it assume execution at a price that

   was never actually available?

6\. Parameter fitting: how many parameters, and were they

   chosen by looking at the whole dataset?

7\. Sample: does the test period contain both a bull and a

   bear regime?

8\. Data alignment: are all series on the same timezone and

   bar-close convention?



Do not summarize. Quote lines.

## The architecture

The mistake is treating the model as a strategy generator. It isn't. It's five different roles, and the generator is the least important one.

**1. Hypothesis** — proposes an idea with a stated economic reason. Prompt for: *"Give me a mechanism, not a pattern."*

**2. Code** — writes the vectorized backtest. Prompt for: *"Shift signals. Include costs. No loops."*

**3. Critic** — attacks the code for look-ahead bias and leakage. Prompt for: *"Find every way this backtest lies."*

**4. Statistician** — corrects for how many things you've tried. Prompt for: *"Deflate the Sharpe for N trials."*

**5. Risk** — sizes it so being wrong doesn't end the account. Prompt for: *"Size for the path, not the destination."*

Three hard gates before any strategy touches real money:

1. The critic finds no leakage
2. The deflated Sharpe clears the multiple-testing bar
3. Out-of-sample performance survives walk-forward

Skip any gate and you've built a very fast way to lose money.

## 1. The backtest engine

If this is wrong, everything downstream is wrong. Build it once, build it correctly, never rewrite it.

python

import numpy as np

import pandas as pd

from dataclasses import dataclass



@dataclass

class Config:

    initial_capital: float = 10_000

    fee_bps: float = 5.0        # round-trip exchange fee

    slippage_bps: float = 3.0   # crypto spreads are wider than you think

    max_leverage: float = 1.0

    periods_per_year: int = 365 # crypto trades 24/7



def backtest(prices: pd.Series, signal: pd.Series, cfg: Config):

    """

    prices: close prices, datetime index

    signal: target position, -1 to +1, computed from data

            available AT that timestamp

    """

    # THE MOST IMPORTANT LINE IN THIS ARTICLE.

    # You act on the NEXT bar, not the one you just saw.

    position = signal.shift(1).fillna(0).clip(

        -cfg.max_leverage, cfg.max_leverage

    )



    returns = np.log(prices / prices.shift(1)).fillna(0)

    gross = position \* returns



    turnover = position.diff().abs().fillna(0)

    costs = turnover \* (cfg.fee_bps + cfg.slippage_bps) / 1e4



    net = gross - costs

    equity = cfg.initial_capital \* np.exp(net.cumsum())



    return pd.DataFrame({

        'position': position,

        'gross': gross,

        'costs': costs,

        'net': net,

        'equity': equity,

    })

That **shift(1)** is the difference between a strategy and a fantasy. Without it you're buying at a price you only knew about after the candle closed. Every AI-generated backtest I've reviewed that showed a Sharpe above 3 was missing it.

## 2. Metrics that don't lie

Return alone tells you nothing. These four tell you whether the thing is tradeable.

python

def metrics(net: pd.Series, cfg: Config):

    r = net.dropna()

    if len(r) < 100:

        return {'error': 'insufficient_data'}



    ann_return = r.mean() \* cfg.periods_per_year

    ann_vol = r.std() \* np.sqrt(cfg.periods_per_year)

    sharpe = ann_return / ann_vol if ann_vol > 0 else 0



    equity = np.exp(r.cumsum())

    peak = equity.cummax()

    dd = (equity - peak) / peak

    max_dd = dd.min()



    # how long you sat underwater — the number that

    # actually decides whether you'd have held on

    underwater = (dd < 0).astype(int)

    longest_dd = underwater.groupby(

        (underwater != underwater.shift()).cumsum()

    ).sum().max()



    return {

        'sharpe': round(sharpe, 2),

        'ann_return': round(ann_return \* 100, 1),

        'max_drawdown': round(max_dd \* 100, 1),

        'longest_dd_days': int(longest_dd),

        'calmar': round(ann_return / abs(max_dd), 2) if max_dd else 0,

        'n_obs': len(r),

    }

Sharpe above 2 on daily crypto data is a red flag, not a trophy. It usually means leakage. Above 3 means it's certain.

## 3. The critic: eight ways your backtest is lying

Give the model your code and this exact list. Do it every time.

Review this backtest for the following errors. For each one,

state PRESENT or ABSENT and quote the line.



1\. Look-ahead: is the signal shifted before becoming a position?

2\. Survivorship: does the asset list include delisted tickers?

3\. Repainting: does any indicator use future data (centered

   moving averages, zigzag, unshifted resample)?

4\. Costs: are fees AND slippage applied on turnover?

5\. Fill assumption: does it assume execution at a price that

   was never actually available?

6\. Parameter fitting: how many parameters, and were they

   chosen by looking at the whole dataset?

7\. Sample: does the test period contain both a bull and a

   bear regime?

8\. Data alignment: are all series on the same timezone and

   bar-close convention?



Do not summarize. Quote lines.

The last instruction matters. Without it you get reassurance instead of review.

## 4. Multiple testing: the part everyone skips

You tested 80 variations. One had a Sharpe of 1.8. Is it real?

Almost certainly not. The expected maximum Sharpe from N random strategies grows with N. Test enough noise and the best of it looks brilliant.

The correction, from Bailey and López de Prado:

python

from scipy.stats import norm



def deflated_sharpe(sharpe, n_trials, n_obs, skew=0.0, kurtosis=3.0):

    """

    sharpe: annualized Sharpe of your BEST strategy

    n_trials: how many variations you tested. Be honest.

    """

    euler = 0.5772156649



    # expected max Sharpe from n_trials of pure noise

    expected_max = (

        (1 - euler) \* norm.ppf(1 - 1/n_trials)

        + euler \* norm.ppf(1 - 1/(n_trials \* np.e))

    )



    denom = np.sqrt(

        1 - skew \* sharpe + ((kurtosis - 1) / 4) \* sharpe\*\*2

    )

    dsr = norm.cdf(

        (sharpe - expected_max) \* np.sqrt(n_obs - 1) / denom

    )



    return {

        'deflated_sharpe': round(dsr, 3),

        'expected_max_from_noise': round(expected_max, 2),

        'verdict': 'PASS' if dsr > 0.95 else 'REJECT',

    }

Run it on your best result. Most people discover their winner is indistinguishable from noise, and that discovery is worth more than any strategy they were about to trade.

Count every variation you tried. Every parameter tweak is a trial. Lying to this function only works on yourself.

## 5. Walk-forward: the only test that matters

One train/test split can be gotten lucky. Walk-forward can't.

python

def walk_forward(prices, strategy_fn, cfg,

                 train_days=180, test_days=60):

    """

    strategy_fn(train_prices) -> fitted params

    Optimize on the past, trade the future, roll forward.

    """

    results = []

    i = 0

    while i + train_days + test_days <= len(prices):

        train = prices.iloc[i : i + train_days]

        test = prices.iloc[i + train_days : i + train_days + test_days]



        params = strategy_fn(train)          # fit on train only

        signal = params['signal_fn']\(test)   # apply to unseen data

        bt = backtest(test, signal, cfg)



        results.append({

            'start': test.index[0],

            \*\*metrics(bt['net'], cfg),

        })

        i += test_days



    df = pd.DataFrame(results)

    return {

        'folds': df,

        'mean_sharpe': round(df['sharpe'].mean(), 2),

        'positive_folds': f"{(df['sharpe'] > 0).sum()}/{len(df)}",

        'worst_fold': round(df['sharpe'].min(), 2),

    }

Judge a strategy on **positive_folds** and **worst_fold**, never on the aggregate. A system that made everything in one fold and bled in the rest is a system that got lucky once.

## 6. Sizing: where accounts actually die

Your edge can be real and still kill you. Direction is the cheap part — surviving the path to being right is the expensive one.

python

def position_size(capital, entry, stop, risk_pct=0.01,

                  max_position_pct=0.20):

    """

    risk_pct: fraction of capital lost if the stop hits

    """

    risk_per_unit = abs(entry - stop)

    if risk_per_unit == 0:

        raise ValueError('stop cannot equal entry')



    units = (capital \* risk_pct) / risk_per_unit

    notional = units \* entry



    cap = capital \* max_position_pct

    if notional > cap:

        units = cap / entry

        notional = cap



    return {

        'units': round(units, 6),

        'notional': round(notional, 2),

        'pct_of_capital': round(notional / capital \* 100, 1),

        'loss_if_stopped': round(units \* risk_per_unit, 2),

    }

One percent risk per trade sounds timid until you model twelve losses in a row — which happens to a 45% win rate roughly once a year. At 1% you're down 11% and still trading. At 5% you're down 46% and need to double just to recover.

## 7. The prompts that actually work

Generic prompts produce generic garbage. These four are the ones that earn their place.

**Hypothesis, not pattern:**

Propose a testable trading hypothesis for BTC on the 4H

timeframe. State the ECONOMIC MECHANISM — who is on the

other side and why they lose. If you cannot name the

counterparty, the idea is a pattern, not an edge.

Then write the exact entry, exit, and invalidation rules.

**Adversarial review:**

You are a quant risk manager whose job is to reject this

strategy. Find every reason it would fail in live trading

that a backtest cannot show. Be specific and hostile.

Assume the author is fooling themselves.

**Regime split:**

Split this backtest into bull, bear, and chop regimes using

a 200-period moving average. Report metrics per regime.

If the edge exists in only one regime, say so directly.

**Honest accounting:**

I have tested N variations of this idea. Compute the

deflated Sharpe ratio for the best result. Tell me plainly

whether this is distinguishable from noise.

That last one is the one people skip. It's the only one that will ever save you money.

## 8. Production: what runs after you deploy

A validated strategy is not a finished strategy. It decays.

python

def health_check(live_returns, backtest_metrics, window=30):

    """Run daily. Halt when it fires."""

    recent = live_returns.tail(window)

    live_sharpe = (

        recent.mean() / recent.std() \* np.sqrt(365)

        if recent.std() > 0 else 0

    )



    equity = np.exp(live_returns.cumsum())

    dd = (equity.iloc[-1] - equity.cummax().iloc[-1]) / equity.cummax().iloc[-1]



    alerts = []

    if live_sharpe < backtest_metrics['sharpe'] \* 0.5:

        alerts.append('SHARPE_DECAY')

    if dd < backtest_metrics['max_drawdown'] / 100 \* 1.5:

        alerts.append('DRAWDOWN_EXCEEDED')



    return {

        'live_sharpe': round(live_sharpe, 2),

        'current_dd': round(dd \* 100, 1),

        'alerts': alerts,

        'action': 'HALT' if alerts else 'CONTINUE',

    }

Decide the kill condition before you deploy, while you're still objective. You will not be objective at the moment it triggers.

## What this actually changes

The bottleneck was never generating ideas. Anyone could think of "buy when RSI is oversold." The bottleneck was the discipline to test it honestly and the skill to build the test.

AI removed the skill barrier. It did not remove the discipline barrier — and now that ideas are free, discipline is the entire edge.

The trader who runs 200 hypotheses a week through this stack and rejects 199 of them is doing the job correctly. The one who runs 200 and trades the best-looking curve is doing something much faster and much worse than what they were doing before.

Same tool. Opposite outcomes.

## The short version

- The **shift(1)** is not optional. Most AI backtests are missing it.
- Sharpe above 2 on daily crypto data means leakage until proven otherwise.
- Count every variation you test. Deflate the Sharpe accordingly.
- Judge on the worst walk-forward fold, not the average.
- Size for the path. Being right and liquidated pays the same as being wrong.
- Decide the kill condition before deploying.

Generation is free now. Validation is the job.

*DYOR. Nothing here is financial advice. All code is illustrative — test it yourself before risking capital.*
