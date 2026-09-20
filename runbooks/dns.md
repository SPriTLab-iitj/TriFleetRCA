# DNS / egress blocked
Symptoms: "lookup ... i/o timeout", "no such host"; NetworkPolicy with Egress and no rules.
Fix: allow egress to kube-dns UDP/TCP 53; check NetworkPolicy in namespace.
