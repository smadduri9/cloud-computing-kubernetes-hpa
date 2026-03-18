# Kubernetes HPA Evaluation

**COEN/MSEN 243 Cloud Computing — Santa Clara University**
**Team:** Lauren Hu, Sriram Madduri, Kehan Chen

Evaluates Kubernetes Horizontal Pod Autoscaler (HPA) performance under variable workloads by comparing a fixed 3-replica deployment against a HPA-managed 1–10 replica deployment.

---

## Prerequisites

**Local demo (no cloud account needed):**
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- Python 3.11+

**GKE deployment (full cloud path):**
- All of the above
- Google Cloud SDK (gcloud CLI, authenticated)
- A GCP project with billing enabled

**Install Python dependencies:**
```bash
pip install locust numpy matplotlib
```

---

## 1. Project Overview

### Directory Structure

```
cloud-computing-kubernetes-hpa/
├── app/                          The FastAPI server deployed to GKE
│   ├── main.py                     REST API with /cpu, /health, /metrics endpoints
│   ├── requirements.txt            Python deps (fastapi, uvicorn, prometheus_client, psutil)
│   └── Dockerfile                  Builds the container image (Python 3.11-slim, non-root)
│
├── k8s/                          Kubernetes manifests applied to the cluster
│   ├── namespace.yaml              Creates the hpa-eval namespace
│   ├── deployment-fixed.yaml       Fixed 3-replica baseline deployment
│   ├── deployment-hpa.yaml         HPA deployment (starts at 1 replica)
│   ├── hpa.yaml                    HPA config: 1–10 replicas, 60% CPU target
│   ├── service.yaml                LoadBalancer services for both deployments
│   └── prometheus/                 Prometheus scraping the app's /metrics endpoint
│       ├── configmap.yaml
│       ├── deployment.yaml
│       └── service.yaml
│
├── locust/
│   └── locustfile.py               18-min phased load test (ramp→spike→sustained→recovery)
│
├── analysis/
│   ├── simulate_results.py         Generates synthetic CSV data (demo without cluster)
│   ├── collect_metrics.py          Queries live Prometheus, exports CSV
│   └── analyze_results.py          Reads CSVs → 4 Matplotlib figures + stats table
│
├── sample_data/                  Experiment output
│   ├── fixed_metrics.csv           Collected from fixed deployment experiment
│   ├── hpa_metrics.csv             Collected from HPA experiment
│   ├── locust_fixed_*.csv          Locust stats from fixed run
│   └── figures/                    4 PNG charts (latency, throughput, cpu_replicas, cost)
│
├── scripts/
│   ├── deploy_gke.sh               Full GKE cluster + image build + deploy
│   ├── deploy_local.sh             Minikube version for local demo
│   └── run_experiment.sh           Runs both experiments back-to-back
│
├── paper/
│   └── final_paper.md              Complete 10-section research paper
│
└── README.md                     This file
```

---

## 2. Quick Demo (no cluster required)

Generate all figures instantly using synthetic data:

```bash
cd /path/to/cloud-computing-kubernetes-hpa
python3 analysis/simulate_results.py
python3 analysis/analyze_results.py
```

Figures are written to `sample_data/figures/`:
- `latency_comparison.png`
- `throughput_comparison.png`
- `cpu_replicas.png`
- `cost_performance.png`

A statistical summary table is printed to stdout.

---

## 3. Local Demo with Minikube

**Step 1:** Deploy everything to Minikube
```bash
bash scripts/deploy_local.sh
```

**Step 2:** Get the NodePort address
```bash
MINIKUBE_IP=$(minikube ip)
HPA_PORT=$(kubectl get svc hpa-eval-hpa-svc -n hpa-eval \
    -o jsonpath='{.spec.ports[0].nodePort}')
```

**Step 3:** Run the load test (separate terminal)
```bash
locust -f locust/locustfile.py \
    --host http://$MINIKUBE_IP:$HPA_PORT \
    --headless --run-time 18m
```

**Step 4:** Watch HPA scale (another terminal)
```bash
kubectl get hpa -n hpa-eval -w
```

**Step 5:** Port-forward Prometheus
```bash
kubectl port-forward svc/prometheus 9090:9090 -n hpa-eval &
```

**Step 6:** Collect metrics after experiment
```bash
python3 analysis/collect_metrics.py --mode hpa \
    --prometheus-url http://localhost:9090
```

**Step 7:** Analyze and plot
```bash
python3 analysis/analyze_results.py
```

---

## 4. GKE Deployment

Deploy to Google Cloud (creates a 3-node e2-standard-2 cluster):

```bash
bash scripts/deploy_gke.sh YOUR_PROJECT_ID us-central1
```

This will:
1. Enable required GCP APIs
2. Create GKE cluster `hpa-eval-cluster`
3. Build and push Docker image to GCR
4. Apply all Kubernetes manifests
5. Wait for pods to be ready
6. Print external IP addresses

Run both experiments sequentially and collect results:
```bash
bash scripts/run_experiment.sh
```

Delete the cluster when done (avoid ongoing charges):
```bash
gcloud container clusters delete hpa-eval-cluster --region us-central1
```

---

## 5. Running Load Tests

The Locust load test implements a 4-phase shape:

| Phase     | Time       | Users   | Spawn Rate |
|-----------|------------|---------|------------|
| Ramp-up   | 0–3 min    | 1→20    | 2/s        |
| Spike     | 3–6 min    | 20→80   | 20/s       |
| Sustained | 6–15 min   | ~60     | —          |
| Recovery  | 15–18 min  | 60→5    | 5/s        |

Traffic mix: 80% CPU-intensive (`/cpu?intensity=low`), 20% health checks (`/`)

**Headless run:**
```bash
locust -f locust/locustfile.py --host http://SERVICE_IP \
    --headless --run-time 18m
```

**Web UI** (open http://localhost:8089 in browser):
```bash
locust -f locust/locustfile.py --host http://SERVICE_IP
```

---

## 6. Collecting and Analyzing Results

Collect from live Prometheus (requires port-forward to be active):
```bash
python3 analysis/collect_metrics.py --mode fixed --prometheus-url http://localhost:9090
python3 analysis/collect_metrics.py --mode hpa   --prometheus-url http://localhost:9090
```

Generate figures from collected (or simulated) data:
```bash
python3 analysis/analyze_results.py
```

Custom CSV paths:
```bash
python3 analysis/analyze_results.py \
    --fixed path/to/fixed_metrics.csv \
    --hpa   path/to/hpa_metrics.csv
```

Output figures:
- `sample_data/figures/latency_comparison.png`
- `sample_data/figures/throughput_comparison.png`
- `sample_data/figures/cpu_replicas.png`
- `sample_data/figures/cost_performance.png`

---

## 7. Application Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Lightweight health check, returns status + hostname |
| `GET /cpu?intensity=low\|medium\|high` | CPU-intensive endpoint (computes 1k/5k/20k primes) |
| `GET /health` | Kubernetes liveness/readiness probe |
| `GET /metrics` | Prometheus text exposition |

Example:
```bash
curl http://SERVICE_IP/cpu?intensity=low
```

---

## 8. Source Code (per 2024 IT policy — all Python code pasted inline)

### app/main.py

```python
import os, time, socket, math
from typing import Literal
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
import psutil
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="HPA Evaluation App", version="1.0.0")

REQUEST_COUNT = Counter("app_requests_total", "Total requests", ["method","endpoint","status_code"])
REQUEST_LATENCY = Histogram("app_request_latency_seconds", "Request latency",
    ["endpoint"], buckets=[0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0])
ACTIVE_REQUESTS = Gauge("app_active_requests", "Active requests")
CPU_USAGE = Gauge("app_cpu_usage_percent", "CPU usage percent")

INTENSITY_MAP = {"low": 1000, "medium": 5000, "high": 20000}

def compute_primes(n):
    primes = []
    candidate = 2
    while len(primes) < n:
        if all(candidate % p != 0 for p in primes if p <= math.isqrt(candidate)):
            primes.append(candidate)
        candidate += 1
    return primes

@app.get("/")
async def root():
    CPU_USAGE.set(psutil.cpu_percent(interval=None))
    return {"status": "ok", "hostname": socket.gethostname(), "version": "1.0.0"}

@app.get("/cpu")
async def cpu_load(intensity: Literal["low","medium","high"] = Query("medium")):
    n = INTENSITY_MAP[intensity]
    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        primes = compute_primes(n)
        elapsed = time.perf_counter() - start
        REQUEST_COUNT.labels(method="GET", endpoint="/cpu", status_code=200).inc()
        REQUEST_LATENCY.labels(endpoint="/cpu").observe(elapsed)
        CPU_USAGE.set(psutil.cpu_percent(interval=None))
        return {"intensity": intensity, "primes_computed": n, "largest_prime": primes[-1],
                "elapsed_seconds": round(elapsed, 4), "hostname": socket.gethostname()}
    finally:
        ACTIVE_REQUESTS.dec()

@app.get("/health")
async def health():
    return {"status": "healthy", "hostname": socket.gethostname()}

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    CPU_USAGE.set(psutil.cpu_percent(interval=None))
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
```

### locust/locustfile.py

```python
from locust import HttpUser, task, between, LoadTestShape


class HPAEvalUser(HttpUser):
    """Simulates a user sending a mix of lightweight and CPU-heavy requests."""

    wait_time = between(1, 3)

    @task(1)
    def health_check(self):
        """Lightweight GET / — 20% of traffic."""
        with self.client.get("/", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(4)
    def cpu_load(self):
        """CPU-intensive GET /cpu — 80% of traffic."""
        with self.client.get(
            "/cpu?intensity=low", catch_response=True, name="/cpu?intensity=low"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


class PhasedLoadShape(LoadTestShape):
    """
    Defines a time-driven load shape that cycles through 4 phases.
    Each tuple: (end_second, target_users, spawn_rate)
    """

    stages = [
        (180,  20,  2),    # ramp-up:   0–3 min,   1→20 users
        (360,  80,  20),   # spike:     3–6 min,   20→80 users
        (900,  60,  5),    # sustained: 6–15 min,  hold ~60 users
        (1080, 5,   5),    # recovery:  15–18 min, ramp down
    ]

    def tick(self):
        run_time = self.get_run_time()

        for end_time, users, spawn_rate in self.stages:
            if run_time <= end_time:
                return (users, spawn_rate)

        return None  # All phases done — stop the test
```

### analysis/simulate_results.py

```python
import os, math, csv
import numpy as np
from datetime import datetime, timedelta

rng = np.random.default_rng(42)
STEP_SECONDS = 15
TOTAL_SECONDS = 18 * 60
TIMESTAMPS = list(range(0, TOTAL_SECONDS + 1, STEP_SECONDS))
N = len(TIMESTAMPS)
BASE_TIME = datetime(2026, 3, 17, 10, 0, 0)

def ts_to_datetime(t):
    return (BASE_TIME + timedelta(seconds=t)).isoformat()

def load_at(t):
    if t <= 180:   return t / 180 * 0.25
    elif t <= 360: return 0.25 + (t - 180) / 180 * 0.75
    elif t <= 900: return 1.0 - (t - 360) / 540 * 0.25
    else:          return max(0.05, 0.75 - (t - 900) / 180 * 0.70)

FIELDNAMES = ["timestamp","elapsed_seconds","experiment","replicas",
              "cpu_utilization_pct","latency_p50_ms","latency_p95_ms",
              "latency_p99_ms","rps","error_rate","active_users"]

def simulate_fixed():
    rows = []
    for t in TIMESTAMPS:
        load = load_at(t)
        replicas = 3
        cpu_per_pod = min(95.0, load * 100.0 / replicas * 3.3)
        cpu_pct = float(np.clip(cpu_per_pod + rng.normal(0, 2.0), 0, 100))
        s = cpu_per_pod / 100.0
        p50 = 80 + 60 + (s - 0.6)**2 * 3000 if s >= 0.6 else 80 + s * 100
        p50 += rng.normal(0, p50 * 0.05)
        p95 = p50 * (1.5 + s * 0.8) + rng.normal(0, p50 * 0.08)
        p99 = p95 * (1.3 + s * 0.5) + rng.normal(0, p95 * 0.08)
        p50 = float(max(50, p50)); p95 = float(max(p50*1.2, p95)); p99 = float(max(p95*1.1, p99))
        rps = float(max(0, min(load * 150, replicas * 12.0) + rng.normal(0, 1.5)))
        err = float(np.clip((cpu_per_pod-85)/15*0.12 if cpu_per_pod > 85 else 0.001, 0, 1))
        rows.append({"timestamp": ts_to_datetime(t), "elapsed_seconds": t, "experiment": "fixed",
                     "replicas": replicas, "cpu_utilization_pct": round(cpu_pct, 2),
                     "latency_p50_ms": round(p50,1), "latency_p95_ms": round(p95,1),
                     "latency_p99_ms": round(p99,1), "rps": round(rps,2),
                     "error_rate": round(err,4), "active_users": int(load*200)})
    return rows

def simulate_hpa():
    rows = []
    current_replicas = 1.0
    target_replicas = 1.0
    for i, t in enumerate(TIMESTAMPS):
        load = load_at(t)
        desired = max(1, min(10, math.ceil(load * 12 / 0.60)))
        if desired > current_replicas and t >= 90:
            past_desired = max(1, min(10, math.ceil(load_at(max(0, t-90)) * 12 / 0.60)))
            target_replicas = past_desired
        elif desired <= current_replicas and i >= 4:
            future_max = max(load_at(TIMESTAMPS[min(i+j, N-1)]) for j in range(4))
            target_replicas = max(desired, max(1, min(10, math.ceil(future_max * 12 / 0.60))))
        current_replicas = 0.3 * target_replicas + 0.7 * current_replicas
        replica_count = max(1, round(current_replicas))
        cpu_per_pod = min(90.0, load * 100.0 / replica_count * 3.3)
        cpu_pct = float(np.clip(cpu_per_pod + rng.normal(0, 2.0), 0, 100))
        s = cpu_per_pod / 100.0
        p50 = 80 + 48 + (s-0.6)**2 * 1500 if s >= 0.6 else 80 + s * 80
        p50 += rng.normal(0, p50 * 0.05)
        p95 = p50 * (1.4 + s * 0.5) + rng.normal(0, p50 * 0.06)
        p99 = p95 * (1.25 + s * 0.3) + rng.normal(0, p95 * 0.07)
        p50 = float(max(50, p50)); p95 = float(max(p50*1.2, p95)); p99 = float(max(p95*1.1, p99))
        rps = float(max(0, min(load * 150, replica_count * 12.0) + rng.normal(0, 1.5)))
        err = float(np.clip(0.001 if cpu_per_pod < 80 else (cpu_per_pod-80)/20*0.05, 0, 1))
        rows.append({"timestamp": ts_to_datetime(t), "elapsed_seconds": t, "experiment": "hpa",
                     "replicas": replica_count, "cpu_utilization_pct": round(cpu_pct, 2),
                     "latency_p50_ms": round(p50,1), "latency_p95_ms": round(p95,1),
                     "latency_p99_ms": round(p99,1), "rps": round(rps,2),
                     "error_rate": round(err,4), "active_users": int(load*200)})
    return rows

def write_csv(rows, filename):
    path = os.path.join(os.path.dirname(__file__), "..", "sample_data", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader(); writer.writerows(rows)
    print(f"  Wrote {len(rows)} rows -> {path}")

if __name__ == "__main__":
    print("Generating synthetic experiment data...")
    write_csv(simulate_fixed(), "fixed_metrics.csv")
    write_csv(simulate_hpa(), "hpa_metrics.csv")
    print("Done.")
```

### analysis/collect_metrics.py

```python
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import json

QUERIES = {
    "cpu_utilization_pct": (
        'avg(app_cpu_usage_percent)'
    ),
    "replicas": (
        'count(count by (instance)(app_requests_total))'
    ),
    "latency_p50_ms": (
        'histogram_quantile(0.50, sum(rate(app_request_latency_seconds_bucket[1m])) by (le)) * 1000'
    ),
    "latency_p95_ms": (
        'histogram_quantile(0.95, sum(rate(app_request_latency_seconds_bucket[1m])) by (le)) * 1000'
    ),
    "latency_p99_ms": (
        'histogram_quantile(0.99, sum(rate(app_request_latency_seconds_bucket[1m])) by (le)) * 1000'
    ),
    "rps": (
        'sum(rate(app_requests_total{status_code="200"}[1m]))'
    ),
    "error_rate": (
        'sum(rate(app_requests_total{status_code!="200"}[1m])) / '
        'sum(rate(app_requests_total[1m]))'
    ),
}

FIELDNAMES = [
    "timestamp", "elapsed_seconds", "experiment",
    "replicas", "cpu_utilization_pct",
    "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "rps", "error_rate",
]

def query_range(prometheus_url, promql, start, end, step=15):
    params = urllib.parse.urlencode({
        "query": promql,
        "start": start,
        "end": end,
        "step": f"{step}s",
    })
    url = f"{prometheus_url.rstrip('/')}/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
    except Exception as exc:
        print(f"  [WARN] Prometheus query failed: {exc}", file=sys.stderr)
        return []
    if data.get("status") != "success":
        return []
    results = data.get("data", {}).get("result", [])
    if not results:
        return []
    return [(float(ts), float(val)) for ts, val in results[0].get("values", [])]

def collect(mode, prometheus_url, duration_minutes=18, step=15):
    print(f"Collecting metrics for experiment={mode} from {prometheus_url}")
    end_time = time.time()
    start_time = end_time - duration_minutes * 60
    series = {}
    for metric, promql in QUERIES.items():
        print(f"  Querying: {metric} ...")
        values = query_range(prometheus_url, promql, start_time, end_time, step)
        series[metric] = values
        print(f"    -> {len(values)} data points")
    if not any(series.values()):
        print("ERROR: No data returned from Prometheus. Is port-forwarding active?", file=sys.stderr)
        sys.exit(1)
    ref_series = series.get("cpu_utilization_pct") or next(v for v in series.values() if v)
    rows = []
    for ts, _ in ref_series:
        row = {
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "elapsed_seconds": int(ts - start_time),
            "experiment": mode,
        }
        for metric, values in series.items():
            val = next((v for t, v in values if abs(t - ts) < step), None)
            row[metric] = round(val, 4) if val is not None else ""
        rows.append(row)
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixed", "hpa"], required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--duration-minutes", type=int, default=18)
    parser.add_argument("--step", type=int, default=15)
    args = parser.parse_args()
    rows = collect(args.mode, args.prometheus_url, args.duration_minutes, args.step)
    output_dir = os.path.join(os.path.dirname(__file__), "..", "sample_data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{args.mode}_metrics.csv")
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {output_path}")

if __name__ == "__main__":
    main()
```

### analysis/analyze_results.py

```python
import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

COLORS = {
    "fixed_p50":  "#2166ac",
    "fixed_p95":  "#4393c3",
    "fixed_p99":  "#92c5de",
    "hpa_p50":    "#d6604d",
    "hpa_p95":    "#f4a582",
    "hpa_p99":    "#fddbc7",
    "hpa_cpu":    "#e08214",
    "hpa_rep":    "#d6604d",
}

PHASE_BOUNDARIES = [0, 180, 360, 900, 1080]
PHASE_LABELS     = ["Ramp-up", "Spike", "Sustained", "Recovery"]
PHASE_COLORS     = ["#f7f7f7", "#fee8c8", "#edf8e9", "#deebf7"]

def phase_bands(ax, max_y):
    for i, (start, end) in enumerate(zip(PHASE_BOUNDARIES, PHASE_BOUNDARIES[1:])):
        ax.axvspan(start, end, alpha=0.15, color=PHASE_COLORS[i], zorder=0)
        ax.text((start + end) / 2, max_y * 0.97, PHASE_LABELS[i],
                ha="center", va="top", fontsize=7, color="#555555", style="italic")

def load_csv(path):
    with open(path, newline="") as f:
        rows = []
        for row in csv.DictReader(f):
            converted = {}
            for k, v in row.items():
                try:
                    converted[k] = float(v) if v != "" else None
                except ValueError:
                    converted[k] = v
            rows.append(converted)
    return rows

def extract(rows, key):
    t = np.array([r["elapsed_seconds"] for r in rows])
    v = np.array([r[key] if r[key] is not None else np.nan for r in rows])
    return t, v

def fig_latency(fixed, hpa, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    fig.suptitle("Response Latency Over Time: Fixed vs HPA", fontsize=13, fontweight="bold")
    max_y = 1100
    for ax, rows, title, prefix in [
        (axes[0], fixed, "Fixed Deployment (3 replicas)", "fixed"),
        (axes[1], hpa,   "HPA Deployment (1–10 replicas)", "hpa"),
    ]:
        t, p50 = extract(rows, "latency_p50_ms")
        _, p95  = extract(rows, "latency_p95_ms")
        _, p99  = extract(rows, "latency_p99_ms")
        phase_bands(ax, max_y)
        ax.plot(t / 60, p99, lw=1.5, alpha=0.6, color=COLORS[f"{prefix}_p99"], label="p99")
        ax.plot(t / 60, p95, lw=2.0, alpha=0.8, color=COLORS[f"{prefix}_p95"], label="p95")
        ax.plot(t / 60, p50, lw=2.5, color=COLORS[f"{prefix}_p50"], label="p50")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Time (minutes)", fontsize=10)
        if ax == axes[0]:
            ax.set_ylabel("Latency (ms)", fontsize=10)
        ax.legend(loc="upper left", fontsize=9)
        ax.set_xlim(0, 18); ax.set_ylim(0, max_y); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "latency_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

def fig_throughput(fixed, hpa, out_dir):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.set_title("Request Throughput (RPS) Over Time: Fixed vs HPA", fontsize=13, fontweight="bold")
    tf, rps_f = extract(fixed, "rps")
    th, rps_h = extract(hpa,   "rps")
    max_y = max(np.nanmax(rps_f), np.nanmax(rps_h)) * 1.15
    phase_bands(ax, max_y)
    ax.plot(tf / 60, rps_f, lw=2.5, color=COLORS["fixed_p50"], label="Fixed (3 replicas)")
    ax.plot(th / 60, rps_h, lw=2.5, color=COLORS["hpa_p50"],   label="HPA (1–10 replicas)")
    ax.set_xlabel("Time (minutes)", fontsize=10)
    ax.set_ylabel("Requests per Second", fontsize=10)
    ax.legend(fontsize=10); ax.set_xlim(0, 18); ax.set_ylim(0, max_y); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "throughput_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

def fig_cpu_replicas(hpa, out_dir):
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax2 = ax1.twinx()
    ax1.set_title("HPA Scaling Behavior: CPU Utilization vs Replica Count", fontsize=13, fontweight="bold")
    t, cpu  = extract(hpa, "cpu_utilization_pct")
    _, reps = extract(hpa, "replicas")
    phase_bands(ax1, 110)
    ax1.plot(t / 60, cpu, lw=2.0, color=COLORS["hpa_cpu"], label="CPU Utilization (%)")
    ax1.axhline(60, color=COLORS["hpa_cpu"], lw=1.0, linestyle="--", alpha=0.6, label="HPA Target (60%)")
    ax2.step(t / 60, reps, lw=2.5, color=COLORS["hpa_rep"], where="post", label="Replica Count")
    ax1.set_xlabel("Time (minutes)", fontsize=10)
    ax1.set_ylabel("CPU Utilization (%)", color=COLORS["hpa_cpu"], fontsize=10)
    ax2.set_ylabel("Replica Count", color=COLORS["hpa_rep"], fontsize=10)
    ax1.set_xlim(0, 18); ax1.set_ylim(0, 110); ax2.set_ylim(0, 12); ax1.grid(True, alpha=0.3)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_dir / "cpu_replicas.png", dpi=150, bbox_inches="tight")
    plt.close()

def fig_cost_performance(fixed, hpa, out_dir):
    COST_PER_POD_HOUR = 0.0535 * (0.1 / 2)
    duration_hours = 18 / 60
    fixed_pod_hours = 3 * duration_hours
    _, reps_h = extract(hpa, "replicas")
    hpa_pod_hours = float(np.nanmean(reps_h)) * duration_hours
    _, p95_f = extract(fixed, "latency_p95_ms")
    _, p95_h = extract(hpa,   "latency_p95_ms")
    _, rps_f = extract(fixed, "rps")
    _, rps_h = extract(hpa,   "rps")
    total_req_f = float(np.nansum(rps_f)) * 15
    total_req_h = float(np.nansum(rps_h)) * 15
    cpk_f = (fixed_pod_hours * COST_PER_POD_HOUR) / (total_req_f / 1000) if total_req_f else 0
    cpk_h = (hpa_pod_hours   * COST_PER_POD_HOUR) / (total_req_h / 1000) if total_req_h else 0
    fig, axes = plt.subplots(1, 3, figsize=(13, 5))
    fig.suptitle("Cost vs Performance Summary", fontsize=13, fontweight="bold")
    bar_kw = dict(width=0.5, edgecolor="black", linewidth=0.7)
    colors = [COLORS["fixed_p50"], COLORS["hpa_p50"]]
    x = [0, 1]; labels = ["Fixed", "HPA"]
    axes[0].bar(x, [fixed_pod_hours, hpa_pod_hours], color=colors, **bar_kw)
    axes[0].set_xticks(x); axes[0].set_xticklabels(labels)
    axes[0].set_title("Pod-Hours Used", fontsize=11); axes[0].set_ylabel("Pod-hours")
    axes[0].grid(True, axis="y", alpha=0.3)
    axes[1].bar(x, [float(np.nanmean(p95_f)), float(np.nanmean(p95_h))], color=colors, **bar_kw)
    axes[1].set_xticks(x); axes[1].set_xticklabels(labels)
    axes[1].set_title("Mean p95 Latency (ms)", fontsize=11); axes[1].set_ylabel("Milliseconds")
    axes[1].grid(True, axis="y", alpha=0.3)
    axes[2].bar(x, [cpk_f, cpk_h], color=colors, **bar_kw)
    axes[2].set_xticks(x); axes[2].set_xticklabels(labels)
    axes[2].set_title("Cost per 1k Requests ($)", fontsize=11); axes[2].set_ylabel("USD")
    axes[2].grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "cost_performance.png", dpi=150, bbox_inches="tight")
    plt.close()

def print_summary(fixed, hpa):
    metrics = [
        ("latency_p50_ms", "Latency p50 (ms)"),
        ("latency_p95_ms", "Latency p95 (ms)"),
        ("latency_p99_ms", "Latency p99 (ms)"),
        ("rps",            "Throughput (RPS)"),
        ("cpu_utilization_pct", "CPU Util (%)"),
        ("replicas",       "Replica Count"),
        ("error_rate",     "Error Rate"),
    ]
    header = f"{'Metric':<25} {'Fixed Mean':>12} {'Fixed Std':>10} {'HPA Mean':>12} {'HPA Std':>10} {'Δ%':>8}"
    print("\n" + "=" * len(header))
    print("STATISTICAL SUMMARY")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for key, label in metrics:
        _, vf = extract(fixed, key)
        _, vh = extract(hpa,   key)
        mf, sf = float(np.nanmean(vf)), float(np.nanstd(vf))
        mh, sh = float(np.nanmean(vh)), float(np.nanstd(vh))
        delta = (mh - mf) / mf * 100 if mf != 0 else 0
        sign = "+" if delta > 0 else ""
        print(f"{label:<25} {mf:>12.2f} {sf:>10.2f} {mh:>12.2f} {sh:>10.2f} {sign}{delta:>7.1f}%")
    print("=" * len(header))

def main():
    parser = argparse.ArgumentParser()
    base_dir = Path(__file__).parent.parent / "sample_data"
    parser.add_argument("--fixed", default=str(base_dir / "fixed_metrics.csv"))
    parser.add_argument("--hpa",   default=str(base_dir / "hpa_metrics.csv"))
    args = parser.parse_args()
    for path in [args.fixed, args.hpa]:
        if not os.path.exists(path):
            print(f"ERROR: {path} not found.", file=sys.stderr)
            sys.exit(1)
    fixed = load_csv(args.fixed)
    hpa   = load_csv(args.hpa)
    print(f"Loaded: {len(fixed)} fixed rows, {len(hpa)} HPA rows")
    out_dir = Path(args.fixed).parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Generating figures...")
    fig_latency(fixed, hpa, out_dir)
    fig_throughput(fixed, hpa, out_dir)
    fig_cpu_replicas(hpa, out_dir)
    fig_cost_performance(fixed, hpa, out_dir)
    print_summary(fixed, hpa)
    print(f"\nAll figures saved to {out_dir}/")

if __name__ == "__main__":
    main()
```

---

## Contact

| Name | Email |
|------|-------|
| Lauren Hu | lhu@scu.edu |
| Sriram Madduri | smadduri@scu.edu |
| Kehan Chen | kchen@scu.edu |
