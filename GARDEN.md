# Garden of Flies

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

The browser's three token names are fictional, not Pons listings. Its agents use
explicit rules. The separate local neural pilot described below now has real
wallets and measured connectome activity. No mainnet transactions have been sent.

Accepted product decisions: voluntary economic exchange rather than duels;
simulated funds first, with the user informed before funding becomes necessary.
All eventual wallets will belong to this experiment. Competition transfers only
funds committed to its rules. The present economy is a model of internal utility;
it has no external customers, real demand, or guaranteed growth.

## Local neural pilot

`Start-Pilot.ps1` opens a loopback-only server at http://127.0.0.1:8767.
It starts paused; Run neural pilot and One round use the actual downloaded
connectome. Each of ten instances has independent membrane state and learning.
The SQLite journal saves financial state, brain checkpoints and events in one
transaction. A failed round stops the process; restart reloads the last checkpoint.
The hosted `pilot.html` is a saved report, not a running cloud brain or remote
control. It displays the report timestamp and disables controls.

The current paper budget is 0.01 ETH total, 0.001 per fly. The local DPAPI vault
contains ten real accounts, bound to this Windows user. No secrets go into the
website. Before any eventual funding, run `Backup-Wallets.ps1` interactively to
create a portable password-encrypted backup and move a copy somewhere safe.
Do not provide the backup password in chat. Funding is not ready yet.

Selected PONS token: `0x39dBED3a2bd333467115dE45665cC57F813C4571`.
Pool: `0x10cc6bd38112cac182db90b6a71d8bb5939526ba`, PONS/WETH, Uniswap V3,
1% fee per swap. `pilot_v3.py` checks chain, canonical pool, token ordering,
launcher configuration, expired launch restrictions, active liquidity, and a
real buy/sell simulation. The probe exists only in an `eth_call` state override;
it is never deployed, funded, or signed. An immediate 0.0001 ETH round trip
returned approximately 0.00009801 WETH before gas at the tested block.

`verify_v3_router.py` compares the complete router runtime with Uniswap's
published 1.3.1 artifact. Only full PUSH32 zero address placeholders may be
substituted with its four immutable address values. This is artifact matching,
not an independent security audit. Source: https://github.com/Uniswap/swap-router-contracts.

`pilot_paper_market.py` buys on a neural inspect-market action with a ten-round
cooldown; financial sizing is explicitly programmed. It uses mainnet quotes,
integer amounts, a 0.0001 ETH per-trade ceiling, and a 0.0002 ETH cash reserve.
It sells positions if needed to restore the 50% limit or stop after 20% losses.
Resource inventory is excluded from net worth. Paper PONS is valued using a
current sell quote. External paper-market cash flows are recorded separately
so total ETH accounting reconciles. Quotes occur sequentially, not at one
atomic portfolio block. Prices may move after a check. Paper trades do not
modify on-chain reserves and do not model gas; they do not forecast profits.

Command-line paper run: `.venv/Scripts/python.exe pilot_runtime.py --steps 3 --market-quotes`.
Setup/read checks: `.venv/Scripts/python.exe pilot_runtime.py --setup`.
Update hosted snapshot: `.venv/Scripts/python.exe export_pilot_report.py`.
No command above sends transactions.

## Still required before funding

The neural runner is paper-only. Live PONS buys, approvals, sales, unwraps,
receipt-driven portfolio accounting, and crash recovery are not integrated.
`pilot_executor.py` is an experimental, disabled resource-settlement component,
not a completed live trading runner. Do not enable it as a funding shortcut.
The local-tested `FlyGarden.sol` resource contract has not been deployed.
Portable encrypted backup and a complete live execution/recovery test remain
required before a funded pilot. `ready_to_fund` intentionally remains false.

Validation: Python accounting, quote-policy, wallet, persistence and router
comparison tests; a local EVM resource-settlement test; ten neural rounds,
including four paper PONS purchases in the last three rounds. Private runtime
data, keys, RPC configuration, dependencies and chain evidence stay ignored.
