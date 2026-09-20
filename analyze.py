#!/usr/bin/env python3
"""results.jsonl -> paper/gen/*.tex|csv + figure.   python analyze.py results.jsonl"""
import argparse, math, pathlib
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

def wilson(h, n, z=1.96):
    if not n: return 0.0, 0.0
    p = h / n; d = 1 + z*z/n; c = p + z*z/(2*n); m = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (c - m) / d, (c + m) / d
def summ(f):
    n, h = len(f), int(f.hit.sum()); lo, hi = wilson(h, n)
    return dict(n=n, hit_rate=round(h/n, 2), ci95=f"[{lo:.2f}, {hi:.2f}]", grounded=round(f.grounded.mean(), 2),
                poison_followed=round(f.poison_followed.mean(), 2), median_latency_s=round(f.latency.median(), 2),
                median_prompt_tok=int(f.prompt_tokens.median()))
def save(df, p):
    df.to_csv(p.with_suffix(".csv"), index=False); p.with_suffix(".tex").write_text(df.to_latex(index=False, escape=True))
    print(f"\n== {p.stem} ==\n{df.to_string(index=False)}")

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("results"); a.add_argument("--outdir", default="paper/gen"); x = a.parse_args()
    out = pathlib.Path(x.outdir); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_json(x.results, lines=True).drop_duplicates(["fault", "rep", "scope", "dedupe", "guard"], keep="last")
    main = df[df.dedupe & df.guard]; order = [s for s in ("pod", "namespace", "cluster") if s in set(main.scope)]

    t1 = pd.DataFrame([dict(scope=s, **summ(main[main.scope == s])) for s in order]).drop(columns="poison_followed")
    save(t1, out / "t1_scope")

    ns = df[df.scope == "namespace"]
    var = {"full": ns[ns.dedupe & ns.guard], "no template dedupe": ns[~ns.dedupe & ns.guard], "no Ring-1 guard": ns[ns.dedupe & ~ns.guard]}
    save(pd.DataFrame([dict(variant=v, **summ(g)) for v, g in var.items() if len(g)]), out / "t2_ablation")

    t3 = main.pivot_table(index="fault", columns="scope", values="hit", aggfunc=lambda s: f"{int(s.sum())}/{len(s)}")[order].reset_index()
    save(t3, out / "t3_fault_scope")

    fig, ax = plt.subplots(figsize=(4, 2.8)); rates = []; err = [[], []]
    for s in order:
        f = main[main.scope == s]; p = f.hit.mean(); lo, hi = wilson(int(f.hit.sum()), len(f))
        rates.append(p); err[0].append(p - lo); err[1].append(hi - p)
    ax.bar(order, rates, yerr=err, capsize=4); ax.set_ylim(0, 1.05); ax.set_ylabel("root-cause hit rate"); ax.set_xlabel("retrieval scope")
    fig.tight_layout(); fig.savefig(out / "f1_scope.pdf"); fig.savefig(out / "f1_scope.png", dpi=200)
