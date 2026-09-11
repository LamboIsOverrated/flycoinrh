# Fly Garden

Work in progress on top of fruitflydev/flycoinrh. Upstream files are preserved.

## Run the paper garden

Serve `dist/` with any static HTTP server and open its index page. No dependency
installation or build is needed. Click Run garden, advance one day, inspect a fly,
filter trades, or export the current simulation. State is local to the open tab;
reloading resets it. Each fly begins with one paper ETH. No funds are required.

`dist/engine.js` is the executable browser/Node simulation. `garden.py` is a
separate Decimal-based accounting foundation for future Python integration.
The browser does not call it. Tests: `node --test test-economy.cjs` and
`python -m unittest test_garden`.

Implemented: ten independent simulated accounts; growers and spinners produce
and exchange nectar/silk; perishable inventories; inventory-sensitive prices;
buyers compare input prices with expected production revenue. Three fictional
tokens trade through constant-product pools with a 0.3% fee and price impact.
Initial pools each hold ten paper ETH and 10,000 tokens; an external simulated
trader has twenty paper ETH. The 60 total paper ETH is conserved. Token supply
is also conserved. Valuations are spot marks, not guaranteed liquidation proceeds.
Resource inventory is excluded from financial net worth.

Token exposure is capped at 50% after each completed day, across all holdings.
The agents buy toward 45% and rebalance toward 48% to leave a buffer. Intra-day
price changes can temporarily breach the limit before rebalancing. Paper amounts
use JavaScript floating-point numbers; live execution must use integer on-chain
units. No gas costs are modeled, so these results do not estimate live returns.

No new mainnet wallets have been generated and no transactions have been sent.
The three token names are fictional, not Pons listings. The agents use explicit
rules, not the upstream connectome. Upstream launching commands remain separate.

Accepted product decisions: voluntary economic exchange rather than duels;
simulated funds first, with the user informed before funding becomes necessary.
All eventual wallets will belong to this experiment. Competition transfers only
funds committed to its rules. The present economy is a model of internal utility;
it has no external customers, real demand, or guaranteed growth.

Remaining before a funded pilot: ten isolated brain sessions, secure per-fly
wallet storage, verified Pons trading contracts/quotes, execution and receipt
tracking, resource settlement, persistence and recovery. Live trading also
needs starting budgets, token eligibility, slippage and loss limits. The original
brain requires the separately downloaded connectome described in README.md.
