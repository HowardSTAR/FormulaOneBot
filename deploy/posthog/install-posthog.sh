#!/usr/bin/env bash
# Run on a separate Ubuntu VM, not on the TurboTears application server.
set -euo pipefail
domain="${1:-}"
if [[ ! "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$ ]]; then
  echo 'Usage: bash install-posthog.sh analytics.your-domain.example' >&2
  exit 2
fi
if [[ ! -f /etc/os-release ]] || ! grep -q '^ID=ubuntu' /etc/os-release; then
  echo 'The official hobby installer requires a separate Ubuntu server.' >&2
  exit 2
fi
if ss -ltn | awk '{print $4}' | grep -Eq ':(80|443)$'; then
  echo 'Ports 80/443 are in use. Use a separate VM to avoid interrupting TurboTears.' >&2
  exit 2
fi
mkdir -p "$HOME/posthog-install"
cd "$HOME/posthog-install"
curl --fail --location --proto '=https' --tlsv1.2 \
  https://github.com/PostHog/posthog/releases/download/hobby-latest/posthog-hobby \
  -o posthog-hobby
chmod 700 posthog-hobby
# Official installer checks Docker, memory, disk, DNS and configures its own stack.
./posthog-hobby --ci --domain "$domain"
