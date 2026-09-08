# Quantitative & Backtesting Architecture Extension
## Module: `backend/app/quant/`

### 1. High-Precision VCP Mathematical Detection
Instead of naive percentage lookbacks, the quant engine uses signal processing to extract swing pivots cleanly:

```python
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

def detect_vcp_contractions(df: pd.DataFrame, prominence: float = 0.03):
    """
    Identifies successive contraction waves using local peak/trough prominence.
    Enforces Minervini VCP rules:
    1. Depth sequence: D_1 > D_2 > ... > D_n
    2. Final contraction depth <= 8% (tightness test)
    3. Volume dry-up ratio: Final swing volume < 50-day SMA volume * 0.5
    """
    highs = df['high'].values
    lows = df['low'].values
    
    # Peak and Trough detection
    peaks, _ = find_peaks(highs, prominence=prominence * highs)
    troughs, _ = find_peaks(-lows, prominence=prominence * lows)
    
    # Calculate wave depths & durations
    contractions = []
    for p, t in zip(peaks[-4:], troughs[-4:]):
        if p < t: # Peak precedes trough in contraction
            depth = (highs[p] - lows[t]) / highs[p]
            duration = t - p
            contractions.append({"peak_idx": int(p), "trough_idx": int(t), "depth": depth, "duration": duration})
            
    is_vcp = all(
        contractions[i]['depth'] > contractions[i+1]['depth'] 
        for i in range(len(contractions) - 1)
    ) if len(contractions) >= 2 else False
    
    return is_vcp, contractions
```

---

### 2. Event-Driven & Vectorized Backtest Integration
To evaluate win rate, profit factor, and maximum drawdown across historical universes:

- **Vectorized Screening (`vectorbt` / `polars`)**: Rapidly backtest Minervini Trend Template qualifications across 10 years of S&P 500 / Nasdaq data to quantify market regime filtering efficiency.
- **Event-Driven Simulation**: Simulate exact trade execution on breakout:
  - **Entry**: Stop-market order placed at \( \text{Pivot Price} + \$0.05 \).
  - **Volume Filter**: Entry only valid if breakout bar volume exceeds \( 1.5 \times \text{SMA50}(Volume) \).
  - **Initial Risk**: Stop-loss pegged strictly to the low of the final contraction (typically 3%–6%).
  - **Profit Taking**: Trailing stop based on 20-day EMA or staged exits at \( 2R \) and \( 3R \).

---

### 3. OpenCode Agent Persona: `@quant-backtester`

Add this specialist agent into your `AGENTS.md` to guide code generation for testing and curve fitting:

```markdown
### 7. Quantitative Backtester Agent (`@quant-backtester`)
- **Mission**: Validates statistical robustness, calculates expectancy metrics, and prevents curve-fitting.
- **Core Responsibilities**:
  - Implement walk-forward optimization for contraction detection thresholds.
  - Compute performance metrics: Sharpe Ratio, Sortino Ratio, Win Rate, Expectancy, and Max Drawdown.
  - Run Monte Carlo simulations on trade distributions to estimate risk of ruin.
  - Verify that volume dry-up parameters do not overfit to specific market regimes.
```
