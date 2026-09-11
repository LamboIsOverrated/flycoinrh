# Garden of Flies

The published website is a read-only observatory. It reads actual ETH and PONS
balances and pool prices through a server-side RPC connection. The title is
exactly Garden of Flies. No visitor controls, paper balances, generated trades,
or simulated prices are served. Missing and stale data are identified.

## Automatic service

Install-Garden-Service.ps1 registers and starts the Garden of Flies Windows task
under the real Windows user. It starts at sign-in and restarts failed processes.
The computer must remain awake and connected. Opening or closing the website
does not affect it. Missing heartbeats are identified after six minutes; neural
measurements expire from display after ten minutes.

live_runner.py reads actual mainnet observations and maintains ten independent
connectome checkpoints. The economic observation and action mapping is programmed,
not evidence that flies understand finance. It does not load earlier paper state.
PONS actions have a one-hour cooldown except for required exits. Resource buys
must have enough expected price margin for buy gas and an 80,000-gas production
allowance. Resources have internal utility, not external customer demand.

## Backup and funding

The initial ceiling is 0.01 ETH total, exactly 0.001 ETH in each of ten wallets,
on Robinhood Chain 4663. Addresses appear on the website and in web/wallets.json.
Do not fund before backup completes. Backup-Garden.ps1 opens a local password
dialog, creates ten portable encrypted keystores, verifies them by decryption,
and offers to save a separate copy. The password never enters the website,
chat, command arguments, or a disk file. Retain the password and backup separately.

Signing keys are DPAPI-encrypted under the real Windows account. RSA-OAEP moved
them from the setup account without writing plaintext keys or changing addresses.
The previous encrypted vault is retained privately. All keys, runtime settings,
and backup files remain ignored and excluded from website output.

The runner waits for verified backup and exact funding. It then deploys the
shared economy from Clover and starts automatically. Deployment uses the same
0.01 ETH budget. Its conservative estimate was about 0.00046 ETH; the maximum
setup fee is 0.0006 ETH. Actual setup gas reduces Clover's trading baseline.
Global loss accounting still includes setup cost. No additional funding is used.

## Live execution and recovery

live_execution.py permits only the compiled settlement deployment, garden
resource actions, exact PONS approvals, and the selected Uniswap V3 route.
Token: 0x39dBED3a2bd333467115dE45665cC57F813C4571.
Pool: 0x10cc6bd38112cac182db90b6a71d8bb5939526ba.
The router matches Uniswap's published SwapRouter02 1.3.1 artifact with
constructor address substitutions. Pinned market runtimes are rechecked before
signing. Artifact matching is not an independent security audit.

Limits: 0.0001 ETH per PONS purchase, 1% slippage, 0.0002 ETH cash reserve,
0.00002 ETH ordinary transaction fee ceiling, 50% token exposure based on sell
quotes, and 20% loss stops. Exits remain available after stops if gas permits.
The pool charges 1% each way. High gas or failed checks can prevent transactions
after funding. Price changes may breach exposure targets between observations;
the next eligible action exits the position. No return is promised.

Signed transactions are encrypted and committed to SQLite before submission.
One unresolved transaction per fly is permitted. Uncertain sends reuse the same
bytes, nonce and hash. Recovery handles missing/reappearing receipts and waits
for 12 matching-block confirmations. Unknown nonce use stops progress.
Very deep reorgs after that threshold are outside automatic recovery policy.
Deployment metadata is recoverable from the confirmed receipt after a crash.

Actual balances remain the financial source of truth. Planned actions are never
reported as executed by a neural checkpoint. The website independently reads
receipts and shows only the recent feed, not an invented lifetime trade count.

Emergency stop: create .garden/STOP. Stop the Windows task for an immediate
process stop. Removing STOP does not itself start the task; start it locally or
sign in again. No visitor-facing execution or stop API exists.

## Development

Build with node build-observatory.cjs. Only web assets and public addresses are
embedded in dist/server/index.js. D1 stores a bounded authenticated heartbeat.
RPC and publisher keys are Sites runtime secrets. The local publisher includes
public telemetry only. Offline paper code is retained solely for engineering
tests and is not served by the website.

Checks: python -m unittest test_live test_pilot test_garden;
node --test test-contract.cjs; node --test test-observatory.cjs.
The full buy, exact approval, sale and native ETH unwrap was also exercised
against mainnet through eth_call state overrides without sending transactions.
