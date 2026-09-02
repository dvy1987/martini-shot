# Spend Control (S5b)

**Capability:** Read `cost_micros` already on job documents. YAML policies cap per-job spend, retries, runaway re-queues (≥N attempts), and project daily budget. On breach the station **acts**: pauses intake for the station, opens a Spend approval in the inbox, and writes a Grafana annotation + incident through MCP (same connector as B-2). Negative or garbage money values coerce to 0.

**Real services:** Firestore (`pc-jobs`, `pc-approvals`, `pc-control`), Grafana MCP.

**How to run tests**

```
python -m pytest tests/test_spend.py tests/test_spend_adversarial.py -q
```

**Evals:** none (deterministic policy engine). Grafana writes in unit tests go through the B-2 dispatch double; live G2 uses the real MCP server.
