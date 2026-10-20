# Server network routing workaround (2026-10-10)

Host 85.198.68.135 can reach GitHub, PyPI and npm, but TCP connections to Debian CDN address 199.232.174.132 and Telegram Bot API address 149.154.166.110 time out. Outgoing firewall policy is ACCEPT, Docker masquerading and forwarding are configured. These observations indicate a destination-specific network problem; they do not establish which upstream operator is responsible.

The alternate Debian address 199.232.42.132 and Telegram address 149.154.167.220 were tested with the original HTTPS hostnames and certificate validation. Telegram getMe succeeded without sending a message. These are temporary routing overrides, not permanent DNS records: reassess them when the provider fixes connectivity or the endpoints change.

Server-local configuration:

- `/etc/hosts` entries for the two hostnames make host diagnostics work.
- `/opt/f1hub-ci/network.env` contains allowlisted `hostname=IPv4` entries consumed by `run-ci.sh`. Docker build and the CI notification container receive `--add-host` without disabling HTTPS verification.
- `/root/FormulaOneBot/docker-compose.network.yml` adds the same mappings to bot, web and worker containers. When adding a worker to an existing installation, extend the bot's `extra_hosts` mappings to it before switching delivery ownership. `deploy-verified.sh` includes the override when present, including during rollback. It contains no secrets and is not copied into application images.

To remove the workaround, remove the marked hosts entries, remove `network.env` and the Compose override, then recreate bot/web/worker with the ordinary Compose configuration. Keep Docker firewall rules unchanged. A timestamped backup is created under `/root/f1hub-network-repair-*` before applying server changes.
