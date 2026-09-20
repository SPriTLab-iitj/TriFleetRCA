#!/usr/bin/env bash
# TriFleetRCA preflight: run once on the GPU box before step 1. Prints OK / MISSING per item, exits 1 if anything is missing.
fail=0; ok(){ printf "  OK       %s\n" "$1"; }; miss(){ printf "  MISSING  %s  ->  %s\n" "$1" "$2"; fail=1; }
echo "== tools"
for t in docker kubectl helm k3d jq git python3 screen curl; do command -v $t >/dev/null && ok "$t" || miss "$t" "install $t"; done
command -v gh >/dev/null && ok gh || echo "  (optional) gh not found - create the repo in the browser instead"
echo "== docker daemon";  docker info >/dev/null 2>&1 && ok "docker running" || miss "docker daemon" "sudo systemctl start docker; add user to docker group"
echo "== GPU";            nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>/dev/null || miss "nvidia-smi" "driver"
echo "== env";            [ "${VLLM_USE_FLASHINFER_SAMPLER:-}" = "0" ] && ok "VLLM_USE_FLASHINFER_SAMPLER=0" || miss "VLLM_USE_FLASHINFER_SAMPLER" "echo 'export VLLM_USE_FLASHINFER_SAMPLER=0' >> ~/.bashrc && source ~/.bashrc"
echo "== vLLM :8000";     M=$(curl -s -m 3 localhost:8000/v1/models | jq -r '.data[0].id' 2>/dev/null)
[ -n "$M" ] && [ "$M" != "null" ] && ok "serving $M" || miss "vLLM on :8000" "README step 0 (takes ~2-5 min to load)"
echo "== Loki :3100";     curl -s -m 3 localhost:3100/ready | grep -q ready && ok "loki ready" || echo "  (later)  Loki not up yet - README step 1"
echo "== disk";           df -h --output=avail "$HOME" | tail -1 | xargs echo "  free in \$HOME:"
[ $fail = 0 ] && echo "ALL GOOD - go to README step 1" || { echo "FIX THE MISSING ITEMS FIRST"; exit 1; }
