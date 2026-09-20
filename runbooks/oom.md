# OOMKilled
Symptoms: pod restarts, Last State: Terminated, Reason: OOMKilled, exit code 137.
Fix: raise memory limit or fix leak; check `kubectl top pod`; VPA recommendation.
