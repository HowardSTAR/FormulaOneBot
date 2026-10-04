#!/usr/bin/env bash
# Read-only checks before considering PostHog on an existing application server.
set -euo pipefail

domain="${1:-}"
if [[ -n "$domain" && ! "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
  echo 'Usage: bash preflight.sh [analytics.example.com]' >&2
  exit 2
fi

echo '=== Operating system ==='
if [[ -r /etc/os-release ]]; then
  awk -F= '/^(NAME|VERSION_ID|ID)=/ {print}' /etc/os-release
fi
echo '=== CPU and current load ==='
nproc
uptime
echo '=== Memory (available matters for sharing the server) ==='
free -h
echo '=== Disk ==='
df -h /
echo '=== Listening HTTP/HTTPS and candidate internal port ==='
if command -v ss >/dev/null; then
  ss -ltn | awk 'NR == 1 || $4 ~ /:(80|443|9009)$/ {print}'
fi
echo '=== Docker and current containers ==='
if command -v docker >/dev/null; then
  docker version --format '{{.Server.Version}}' || true
  docker compose version || true
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' || true
else
  echo 'Docker is not installed. This check does not install it.'
fi
if [[ -n "$domain" ]]; then
  echo "=== DNS for $domain ==="
  getent ahostsv4 "$domain" | awk '{print $1}' | sort -u || true
fi

memory_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
disk_kib=$(df -Pk / | awk 'NR == 2 {print $4}')
echo '=== Capacity check for sharing the server ==='
if (( $(nproc) < 4 || memory_kib < 16*1024*1024 || disk_kib < 30*1024*1024 )); then
  echo 'Insufficient spare capacity against the PostHog hobby requirements.'
  echo 'Do not launch PostHog alongside the running bot without a capacity decision.'
else
  echo 'Basic spare capacity is present. Current load and proxy configuration still need review.'
fi
echo 'No packages, containers, firewall rules or nginx settings were changed.'
