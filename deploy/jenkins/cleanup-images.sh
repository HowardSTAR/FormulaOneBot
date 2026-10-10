#!/usr/bin/env bash
# Remove application images only. Keep production, rollback and all containers.
set -Eeuo pipefail

protected=()
for ref in formulaonebot-app:latest formulaonebot-rollback:previous; do
  image=$(docker image ls --no-trunc --quiet "$ref")
  if [[ -n "$image" ]]; then
    protected+=("$(docker image inspect "$ref" --format '{{.Id}}')")
  fi
done
# If inspection fails, stop rather than risk deleting a protected image.
containers=$(docker ps -aq)
if [[ -n "$containers" ]]; then
  while IFS= read -r container; do
    protected+=("$(docker inspect "$container" --format '{{.Image}}')")
  done <<< "$containers"
fi

# Include legacy tagged candidates and new labelled images that lost their tags.
images=$(docker image ls --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}')
labelled=$(docker image ls --no-trunc --filter label=ru.f1hub.ci.app=true --format '{{.ID}}')
while read -r image ref; do
  [[ -n "$image" ]] || continue
  case "$ref" in
    formulaonebot-ci:*|formulaonebot-app:*|formulaonebot-rollback:*|formulaonebot-bot:*|formulaonebot-web:*) ;;
    *) [[ $'\n'"$labelled"$'\n' == *$'\n'"$image"$'\n'* ]] || continue ;;
  esac
  keep=0
  for saved in "${protected[@]}"; do
    if [[ "$image" == "$saved" ]]; then keep=1; break; fi
  done
  [[ "$keep" == 0 ]] || continue
  target="$ref"
  [[ "$ref" != '<none>:<none>' ]] || target="$image"
  # Never force removal: Docker also protects images referenced by containers.
  if ! docker image rm "$target"; then
    echo "Could not remove application image $target; leaving it in place." >&2
  fi
done <<< "$images"
