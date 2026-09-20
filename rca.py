#!/usr/bin/env python3
"""TriFleetRCA v1: Loki logs + K8s events -> scoped retrieval (pod|namespace|cluster, TriCalRAG)
-> runbooks behind a Ring-1 ingest guard (TriShieldRAG) -> one local LLM -> cited JSON root cause."""
import argparse, glob, json, os, re, subprocess, time, requests
from rank_bm25 import BM25Okapi
from openai import OpenAI

LLM = OpenAI(base_url=os.getenv("LLM_URL", "http://localhost:8000/v1"), api_key="x")
MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-14B-Instruct")
LOKI = os.getenv("LOKI_URL", "http://localhost:3100")

# ---------- evidence ----------
def sh(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
def loki_lines(selector, minutes=10, limit=2000):
    end = int(time.time() * 1e9); start = end - minutes * 60 * int(1e9)
    r = requests.get(f"{LOKI}/loki/api/v1/query_range", timeout=20,
                     params={"query": selector, "start": start, "end": end, "limit": limit, "direction": "backward"}).json()
    out = []
    for s in r.get("data", {}).get("result", []):
        pod = s["stream"].get("pod", "?")
        out += [f"[log pod={pod}] {line[:300]}" for _, line in s["values"]]
    return out
def k8s_lines(ns, pod=None):
    ev = sh(f"kubectl -n {ns} get events --sort-by=.lastTimestamp -o custom-columns=T:.lastTimestamp,K:.involvedObject.kind,N:.involvedObject.name,R:.reason,M:.message --no-headers | tail -60")
    pods = sh(f"kubectl -n {ns} get pods -o wide --no-headers")
    lines = [f"[event] {l}" for l in ev.splitlines()] + [f"[pod] {l}" for l in pods.splitlines()]
    if pod:
        d = sh(f"kubectl -n {ns} describe pod {pod} | sed -n '/Last State/,/Ready/p;/Events/,$p' | tail -40")
        lines += [f"[describe {pod}] {l}" for l in d.splitlines() if l.strip()]
    st = sh(f"kubectl -n {ns} get pods -o jsonpath='{{range .items[*]}}{{.metadata.name}}{{\" restarts=\"}}{{.status.containerStatuses[0].restartCount}}{{\" state=\"}}{{.status.containerStatuses[0].state}}{{\" lastState=\"}}{{.status.containerStatuses[0].lastState}}{{\"\\n\"}}{{end}}'")
    lines += [f"[container-state] {l}" for l in st.splitlines() if l.strip()]
    np_ = sh(f"kubectl -n {ns} get networkpolicy -o custom-columns=N:.metadata.name,T:.spec.policyTypes,I:.spec.ingress,E:.spec.egress --no-headers")
    return lines + [f"[netpol] {l}" for l in np_.splitlines()]
def evidence(scope, ns, pod=None, minutes=10):
    if scope == "pod":       return loki_lines(f'{{namespace="{ns}",pod="{pod}"}}', minutes) + k8s_lines(ns, pod)
    if scope == "namespace": return loki_lines(f'{{namespace="{ns}"}}', minutes) + k8s_lines(ns)
    return loki_lines('{namespace=~".+"}', minutes, 4000) + k8s_lines(ns)       # cluster

# ---------- retrieval: template dedupe + BM25 ----------
BOOST = ["error", "fail", "failed", "refused", "timeout", "oomkilled", "backoff", "not", "found", "unknown", "denied"]
def template(line): return re.sub(r"\d+|0x[0-9a-f]+|[0-9a-f]{8,}", "<*>", line.lower())
def retrieve(lines, query, k=25, dedupe=True):
    if not lines: return []
    count, uniq = {}, []
    for l in lines:
        t = template(l) if dedupe else l
        count[t] = count.get(t, 0) + 1
        if count[t] == 1 or not dedupe: uniq.append(l)
    key = (lambda l: template(l)) if dedupe else (lambda l: l)
    bm = BM25Okapi([re.findall(r"\w+", template(l)) for l in uniq])
    scores = bm.get_scores(re.findall(r"\w+", query.lower()) + BOOST)
    rank = sorted(range(len(uniq)), key=lambda i: -(scores[i] + (0.5 * min(count[key(uniq[i])], 20) / 20 if dedupe else 0)))
    return [f"E{i+1}: {uniq[j]}" + (f" (x{count[key(uniq[j])]})" if dedupe else "") for i, j in enumerate(rank[:k])]

# ---------- Ring-1 ingest guard ----------
BLOCK = [r"ignore (all |previous )?instructions", r"the answer is", r"delete (namespace|ns) ", r"--force", r"rm -rf", r"resolves every"]
def runbooks(guard=True):
    ok, rejected = [], []
    for f in sorted(glob.glob("runbooks/*.md")):
        txt = open(f).read()
        if guard and any(re.search(p, txt, re.I) for p in BLOCK): rejected.append(f); continue
        ok.append(f"[runbook {f}]\n{txt.strip()}")
    return ok, rejected

# ---------- LLM ----------
SYS = ('You are an SRE. Use ONLY the evidence. Reply with JSON: {"root_cause": str, "evidence_ids": ["E3",...], '
       '"runbook_step": str, "confidence": 0-1}. No prose.')
def ask(prompt):
    kw = dict(model=MODEL, temperature=0, max_tokens=400,
              messages=[{"role": "system", "content": SYS}, {"role": "user", "content": prompt}])
    try: r = LLM.chat.completions.create(response_format={"type": "json_object"}, **kw)
    except Exception: r = LLM.chat.completions.create(**kw)
    txt = r.choices[0].message.content.strip().strip("`").removeprefix("json").strip()
    try: ans = json.loads(txt); assert isinstance(ans, dict)
    except Exception: ans = {"root_cause": txt[:200], "evidence_ids": [], "runbook_step": "", "confidence": 0.0}
    return ans, r.usage.prompt_tokens, r.usage.completion_tokens
def rca(alert, scope, ns, pod=None, minutes=10, dedupe=True, guard=True):
    raw = evidence(scope, ns, pod, minutes); ev = retrieve(raw, alert, dedupe=dedupe)
    rbs, rejected = runbooks(guard)
    prompt = f"ALERT: {alert}\n\nEVIDENCE:\n" + "\n".join(ev) + "\n\nRUNBOOKS:\n" + "\n\n".join(rbs)
    t0 = time.time(); ans, ptok, ctok = ask(prompt)
    ids = [str(i) for i in ans.get("evidence_ids") or []] if isinstance(ans.get("evidence_ids"), list) else []
    ans.update(latency_s=round(time.time() - t0, 2), prompt_tokens=ptok, completion_tokens=ctok, n_raw=len(raw),
               n_evidence=len(ev), rejected_runbooks=rejected, cited=[e for e in ev if e.split(":")[0] in ids])
    return ans

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--alert", required=True); a.add_argument("--ns", default="online"); a.add_argument("--pod")
    a.add_argument("--scope", default="namespace", choices=["pod", "namespace", "cluster"])
    a.add_argument("--no-dedupe", action="store_true"); a.add_argument("--no-guard", action="store_true")
    x = a.parse_args(); print(json.dumps(rca(x.alert, x.scope, x.ns, x.pod, dedupe=not x.no_dedupe, guard=not x.no_guard), indent=2))
