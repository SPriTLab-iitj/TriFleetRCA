<!-- Public repo README. Fill the TODOs at step 8, then: git mv README.md docs/WORKLOG.md && git mv README.public.md README.md -->

# TriFleetRCA

**On-Premise LLM Root Cause Analysis for Kubernetes**

Rohit Patel, TODO co-authors · Dept. of Computer Science and Engineering, IIT Jodhpur

[![arXiv](https://img.shields.io/badge/arXiv-TODO-b31b1b.svg)](https://arxiv.org/abs/TODO) [![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE) [![DOI](https://zenodo.org/badge/DOI/TODO.svg)](https://doi.org/TODO)

An alert fires on a Kubernetes cluster. A local open-weight LLM reads the site's own Loki logs and Kubernetes events, consults runbooks that pass an ingest guard, and answers with a root cause and the exact evidence lines it used. Everything runs on one workstation GPU. No log leaves the site.

## Abstract

TODO — paste the paper abstract here (one paragraph).

## Contributions

1. A reproducible live fault-injection testbed for LLM root cause analysis on Kubernetes: 4 faults, a fresh namespace per trial, and a log window bounded to injection time.
2. A measurement of how retrieval **scope** (pod / namespace / cluster) affects root-cause accuracy on live logs **and** Kubernetes events.
3. A measurement of how often a local LLM follows a **poisoned runbook** during an incident, and what an ingest guard prevents.
4. A *grounded-citation* metric: an answer counts only if a cited line actually contains the fault signal.

## Results

TODO — after `analyze.py`, paste the three tables (`paper/gen/*.csv`) and the headline sentence. Keep n and the 95% CI on every rate.

| Retrieval scope | n | Hit rate (95% CI) | Grounded | Median latency |
|---|---|---|---|---|
| pod | TODO | | | |
| namespace | TODO | | | |
| cluster | TODO | | | |

Poisoned runbook: followed in TODO of trials with the guard off, TODO with the guard on.

## Architecture

```mermaid
flowchart LR
    F[injected fault] --> APP[k3d cluster: podinfo + backend]
    APP --> LOKI[(Loki)] & EV[kube events]
    LOKI & EV --> S{scope: pod / namespace / cluster}
    S --> R[template dedupe + BM25, top 25]
    RB[runbooks, one poisoned] --> G{Ring-1 ingest guard} --> P[prompt]
    R --> P --> LLM[Qwen2.5-14B on vLLM, local GPU]
    LLM --> OUT[JSON: root_cause, cited lines, runbook step]
```

## Setup

Requires Docker, k3d, kubectl, Helm, Python 3.10+, and one NVIDIA GPU with ~58 GB free.
Reference machine: NVIDIA RTX PRO 6000 Blackwell Max-Q (96 GB), driver 595.58.03, CUDA 13.2.

```bash
git clone https://github.com/TODO/trifleetrca && cd trifleetrca
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
bash scripts/preflight.sh

# model
export VLLM_USE_FLASHINFER_SAMPLER=0
vllm serve Qwen/Qwen2.5-14B-Instruct --dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.6 --port 8000 &

# cluster + logs
k3d cluster create site --servers 1 --agents 2 --k3s-arg "--disable=traefik@server:*"
helm repo add grafana https://grafana.github.io/helm-charts && helm repo update
kubectl create ns logging
helm install loki grafana/loki-stack -n logging --set loki.persistence.enabled=false --set promtail.enabled=true --set grafana.enabled=false
kubectl -n logging port-forward svc/loki 3100:3100 &
```

## Reproduce the paper

```bash
python sweep.py --reps 5 --out results.jsonl    # ~75 min, resumable
python analyze.py results.jsonl                 # -> paper/gen/*.csv|.tex, f1_scope.pdf
```

`results.jsonl` from the paper run is included, so `analyze.py` reproduces every table without a GPU.

## Single RCA

```bash
python rca.py --alert "pods restarting in namespace online" --ns online --scope namespace
```

Returns JSON: `root_cause`, `evidence_ids`, `cited`, `runbook_step`, `confidence`, `latency_s`, `rejected_runbooks`.

Environment: `LLM_URL`, `LLM_MODEL`, `LOKI_URL`.

## Repository layout

| Path | What |
|---|---|
| `rca.py` | pipeline: evidence → retrieval → guard → LLM → cited JSON |
| `sweep.py` | experiment driver, one namespace per trial, resumable |
| `analyze.py` | results → tables and figure |
| `runbooks/` | 4 runbooks plus `poison.md`, the tampered file used in the guard experiment |
| `scripts/preflight.sh` | environment check |
| `paper/` | LaTeX source and generated tables |
| `results.jsonl` | raw results from the paper run |

## Limitations

4 fault types, one model, one cluster, temperature 0, a demo application, regex-based grading, and an ingest guard built from a short pattern list that is tuned to a loudly worded attack. See §Limitations in the paper.

## Built on

- TriCalRAG — retrieval scopes (arXiv:2609.14762)
- TriShieldRAG — Ring-1 ingest guard (arXiv:2607.23838)

## Citation

```bibtex
TODO — paste from arXiv once the ID is assigned
```

## License

Apache-2.0.
