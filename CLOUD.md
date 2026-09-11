# Cloud garden service

The Dockerfile runs `live_runner.py`, not the upstream roaming browser demo.
It installs the pinned pilot dependencies, downloads the official FlyEM dataset,
builds the graph, and compiles the two Solidity artifacts in separate stages.
Only the graph, annotations and compiled artifacts enter the final image.
No ignored local `data/` or `build/` folder is needed in the Git checkout.
The initial build downloads about 1.1 GB and needs several GB of builder RAM.

## Deployment settings

Use one replica. Attach a persistent volume at `/app/.garden` for the transaction
journal and neural checkpoints. Do not mount over `/app`, `/app/build` or `/app/data`.
Leave the Docker start command unchanged. Use `/healthz` as the health-check path;
the service listens on the platform's `PORT` (8080 by default) and starts itself.
The normal Railway domain serves the spectator website at `/`, live chain data
at `/api/status`, and health checks at `/healthz`. The website works while the
runner waits for backup or funding. It has no start button or signing controls.

Required runtime secret:

- `GARDEN_RPC_URL`: the authenticated Robinhood Chain mainnet RPC URL.

Optional, only to mirror neural activity to the separate Sites website (these
settings are not needed for the Railway website):

- `GARDEN_SITE_URL`: the existing Garden of Flies website URL.
- `GARDEN_PUBLISHER_KEY`: the matching Sites heartbeat secret.
- `GARDEN_SITE_TOKEN`: the existing private Sites API access token.

For wallet recovery and signing:

- `GARDEN_STATE_KEY`: a stable, random 32-byte key encoded as base64. It encrypts
  saved signed transactions. Retain it with the persistent journal; do not rotate
  it while any transaction is unresolved.
- `GARDEN_WALLET_BACKUP_JSON`: the complete encrypted portable backup JSON, stored
  as a runtime secret. Alternatively use `GARDEN_WALLET_BACKUP_FILE` pointing to
  a secret-mounted file outside the repository.
- `GARDEN_WALLET_PASSWORD`: the backup password, entered directly into the cloud
  provider's secret settings. Never put it in GitHub, Docker build arguments, or chat.

Without wallet recovery settings the garden observes actual chain balances and
waits for backup; it does not create replacement wallets or sign transactions.
The imported backup must match the existing ten public addresses exactly.
Linux uses AES-256-GCM for private transaction state; Windows retains DPAPI.

Stop and disable the Windows Garden of Flies task before activating the cloud
signer. Never run two independent signers for these wallets. This pilot has not
sent any transaction, so its cloud journal can start empty. If that changes,
migrate its complete journal and signing-state protection before switching hosts.
The initial funding gate rejects wallets with unexplained prior nonces.

Complete and retain the encrypted backup before funding. The approved half-funding operating budget is 0.012039647790757096 ETH total,
including gas and deployment. The address-bound allocations in pilot_config.json
exclude the reserved half from all execution balances, exposure and fee checks.
The reserved ETH remains in the wallets; this is an application spending limit.
Initial activation requires each configured allocation and no token deposits.
Deployment, cloud environment configuration and funded execution are separate
from a successful Docker build.
