# E3: Cost Engine

Implement each cost sub-model and compose them into CostEngine.

## Stories

- [ ] **E3-S01** `MVP` — Implement CommissionModel.calculate() for "fixed" model type
- [ ] **E3-S02** `MVP` — Implement SpreadModel.calculate() for "fixed" and "dynamic" model types (base spread + volatility multiplier + time-of-day curve)
- [ ] **E3-S03** `MVP` — Implement SlippageModel.calculate() for "fixed_pct" model type
- [ ] **E3-S04** `MVP` — Implement CostEngine: compose sub-models, expose entry_costs() and exit_costs() returning CostBreakdown
- [ ] **E3-S05** `MVP` — Unit tests: verify commission, spread, slippage calculations against hand-computed expected values across multiple scenarios
- [ ] **E3-S06** `P2` — Implement CommissionModel.calculate() for "per_share" and "tiered" model types
- [ ] **E3-S07** `P2` — Implement CommissionModel.calculate() for "zero" model type (monthly free volume threshold)
- [ ] **E3-S08** `P2` — Implement SlippageModel.calculate() for "volume_based" model type
- [ ] **E3-S09** `P2` — Implement SpreadModel with "market" mode (accept live bid/ask override)
- [ ] **E3-S10** `P2` — Implement OvernightModel.calculate(): reference rate + broker markup, day divisor, triple swap day
- [ ] **E3-S11** `P2` — Implement FX conversion cost: apply fx_conversion_pct when position currency differs from account base_currency
- [ ] **E3-S12** `P2` — Implement DividendModel: stock withholding calculation by country code
- [ ] **E3-S13** `P2` — Implement DividendModel: CFD dividend adjustment (credit for longs, charge for shorts)
- [ ] **E3-S14** `P2` — Unit tests: overnight, FX, dividend cost calculations
