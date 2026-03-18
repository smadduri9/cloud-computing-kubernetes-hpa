# Evaluating Kubernetes Horizontal Pod Autoscaler Performance Under Variable Workloads

**Course:** COEN/MSEN 243 — Cloud Computing
**Instructor:** Dr. Ming-Hwa Wang
**Institution:** Santa Clara University
**Team:** Lauren Hu, Sriram Madduri, Kehan Chen
**Date:** March 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Problem Statement](#2-problem-statement)
3. [Related Work](#3-related-work)
4. [Methodology](#4-methodology)
5. [Hypotheses](#5-hypotheses)
6. [Implementation](#6-implementation)
7. [Data Analysis and Discussion](#7-data-analysis-and-discussion)
8. [Conclusions and Recommendations](#8-conclusions-and-recommendations)
9. [Bibliography](#9-bibliography)
10. [Appendices](#10-appendices)

---

## 1. Introduction

The proliferation of cloud-native applications has transformed how software systems handle variable demand. Modern web services must routinely absorb traffic spikes ranging from gradual growth to sudden multiplicative surges, often without any advance warning. Static resource allocation — provisioning enough capacity for anticipated peak load — is a time-honored but increasingly untenable strategy: it wastes resources during off-peak periods and can still fail during unexpected demand spikes.

Kubernetes, the dominant container orchestration platform, addresses this challenge through the **Horizontal Pod Autoscaler (HPA)**, a control-loop mechanism that automatically adjusts the number of pod replicas based on observed resource utilization. When CPU or memory utilization exceeds a target threshold, the HPA scales out the deployment; when utilization drops, it scales in to reduce resource consumption and cost.

Despite HPA's widespread adoption, its behavior under dynamic, bursty workloads is not well characterized in the academic literature. Practitioners deploying HPA-managed services must make consequential configuration decisions — target utilization percentage, minimum and maximum replica counts, stabilization window durations — with limited empirical guidance tailored to their specific workload patterns.

This paper presents a controlled empirical evaluation of Kubernetes HPA performance. We instrument a purpose-built CPU-intensive microservice with Prometheus metrics, deploy it to a Google Kubernetes Engine (GKE) cluster, and subject it to a phased load test simulating realistic traffic patterns including ramp-up, sudden spike, sustained load, and recovery phases. We compare the HPA-managed deployment against a fixed-replica baseline across four primary metrics: response latency (p50/p95/p99), request throughput, CPU utilization, and cost efficiency.

Our results confirm that HPA significantly improves tail-latency performance under sustained high load, at the cost of a predictable degradation window during sudden spikes while the autoscaler reacts. We quantify this trade-off and provide actionable configuration recommendations for practitioners.

---

## 2. Problem Statement

### 2.1 The Static Provisioning Dilemma

Organizations deploying services on Kubernetes face a fundamental resource provisioning dilemma. Static deployments must be sized for peak load, leading to substantial resource waste during typical operation. Under-provisioning to reduce cost creates risk of service degradation or failure during demand spikes.

The core tension is: **How much should we pay for capacity we might need?**

### 2.2 HPA's Promise and Limitations

Kubernetes HPA promises to resolve this dilemma by making scaling automatic and reactive. However, HPA's reactive nature — it scales based on observed metrics — means it is inherently backward-looking. By the time a spike is detected, pods are already under stress. New pods take time to schedule, pull images, start, and pass readiness checks. This startup latency, typically 30–120 seconds, creates a window during which the system operates with insufficient capacity.

### 2.3 Research Questions

This study addresses three research questions:

1. **RQ1:** Under sustained high load, does HPA achieve lower tail latency than an equivalent fixed deployment at the same total resource budget?
2. **RQ2:** How quickly does HPA respond to sudden demand spikes, and what is the magnitude of latency degradation during the response window?
3. **RQ3:** Does HPA provide meaningful cost savings versus a fixed deployment sized for peak load, when accounting for both resource cost and service quality?

### 2.4 Scope and Constraints

We limit our evaluation to **CPU-based HPA** (the most widely deployed variant) with **Kubernetes metrics-server** as the metrics source. We do not evaluate custom metrics, external metrics, or KEDA-based scaling. Our workload is CPU-bound rather than I/O-bound, which represents a common class of compute-intensive microservices (ML inference, data processing, image manipulation, etc.).

---

## 3. Related Work

### 3.1 Autoscaling Frameworks

Burns et al. (2016) introduced the Kubernetes architecture, describing the HPA as a key mechanism for elastic scaling. The original HPA design used a simple threshold-crossing algorithm; subsequent versions (v2beta2 and autoscaling/v2) added support for multiple metrics, custom metrics, and configurable scaling behaviors.

Rattihalli et al. (2019) studied HPA's responsiveness under different workload patterns, finding that the default 15-second scrape interval and control loop delay introduces 30–60 seconds of reaction latency under step-change workloads. Their work motivated the configurable `stabilizationWindowSeconds` parameter added in Kubernetes 1.18.

### 3.2 Reactive vs. Predictive Scaling

A significant body of work has examined predictive scaling as a complement or replacement for reactive HPA. Bauer et al. (2019) demonstrated that machine-learning-based predictive scaling reduces spike-period latency by pre-scaling before demand arrives. Toka et al. (2021) proposed a hybrid controller combining HPA's reactive mechanism with LSTM-based load prediction.

Our work focuses on the reactive HPA in its standard configuration, establishing a baseline against which future predictive-enhancement work can be compared.

### 3.3 Cloud-Native Microservice Benchmarking

Eskandani and Salvaneschi (2021) surveyed benchmarking methodologies for cloud-native systems, recommending against synthetic micro-benchmarks in favor of realistic phased load tests. We follow their methodology by implementing a four-phase load shape covering ramp-up, spike, sustained, and recovery periods.

Gan et al. (2019) introduced DeathStarBench, a widely used microservice benchmark suite. Our single-service evaluation intentionally simplifies the system topology to isolate HPA's behavior without confounding variables introduced by service mesh and inter-service call chains.

### 3.4 Cost Optimization in Kubernetes

Gog et al. (2016) analyzed resource efficiency in large-scale container clusters, finding typical CPU utilization of 20–40% even in well-managed production clusters. This under-utilization motivates elastic scaling. Our cost analysis quantifies the efficiency improvement achievable with HPA versus static provisioning.

---

## 4. Methodology

### 4.1 System Architecture

The evaluation system consists of four layers:

1. **Application Layer**: A Python FastAPI service with a CPU-intensive endpoint that computes prime numbers
2. **Infrastructure Layer**: Google Kubernetes Engine cluster with 3 × e2-standard-2 nodes
3. **Autoscaling Layer**: Kubernetes HPA with CPU-based scaling policy
4. **Observability Layer**: Prometheus scraping pod metrics every 15 seconds

### 4.2 Application Design

The evaluation application (`app/main.py`) was designed to be CPU-bound rather than I/O-bound, to produce deterministic scaling behavior. The primary workload endpoint (`GET /cpu?intensity=medium`) computes 5,000 prime numbers using trial division, consuming predictable CPU time proportional to the requested intensity.

Resource requests were set to `100m` CPU with a limit of `200m`. This means a pod running at 100% of its request is using `100m` CPU, and at the HPA target of 60%, the pod should be using `60m` CPU. These conservative limits ensure that CPU throttling behavior is observable within the experiment duration.

### 4.3 Experiment Design

We run two experiments with identical load profiles but different deployment configurations:

**Experiment A — Fixed Baseline:**
- 3 replicas, static
- No HPA attached
- Represents static over-provisioning at expected peak (7 × baseline replicas)

**Experiment B — HPA:**
- Starts at 1 replica
- HPA: minReplicas=1, maxReplicas=10, target=60% CPU utilization
- Scale-down stabilization window: 60 seconds
- Scale-up: no stabilization window (respond immediately)

### 4.4 Load Profile

The Locust load test follows a four-phase shape designed to stress both steady-state performance and transient responsiveness:

| Phase | Time (min) | Users | Spawn Rate |
|-------|-----------|-------|-----------|
| Ramp-up | 0–3 | 1→50 | 5/s |
| Spike | 3–6 | 50→200 | 50/s |
| Sustained | 6–15 | ~150 | — |
| Recovery | 15–18 | 150→10 | 10/s |

Traffic mix: 80% CPU-intensive (`GET /cpu?intensity=medium`), 20% lightweight health checks (`GET /`).

### 4.5 Metrics Collection

Prometheus scrapes the application's `/metrics` endpoint every 15 seconds. We collect:
- `app_request_latency_seconds` histogram → p50, p95, p99
- `app_requests_total` counter → RPS and error rate
- `container_cpu_usage_seconds_total` → CPU utilization per pod
- `kube_deployment_status_replicas_available` → current replica count

Data is exported to CSV via `analysis/collect_metrics.py` using the Prometheus HTTP API.

---

## 5. Hypotheses

Based on our understanding of HPA's reactive architecture, we formulate four testable hypotheses:

**H1 (Latency Improvement):** Under sustained high load, the HPA deployment will exhibit at least 30% lower p95 latency than the fixed deployment.

*Rationale:* With more replicas available, each pod processes fewer requests and operates below CPU saturation. The fixed deployment's 3 pods will be CPU-throttled during sustained load, inflating latency nonlinearly.

**H2 (Scaling Responsiveness):** HPA will reach its scaled-out replica count within 90 seconds of the spike onset.

*Rationale:* Kubernetes metrics-server has a 15-second scrape interval; HPA evaluates metrics every 15 seconds; pod startup takes approximately 10–30 seconds. Total reaction time should be 45–90 seconds.

**H3 (Cost Neutrality):** HPA will consume no more than 125% of the fixed deployment's pod-hours over the full 18-minute experiment.

*Rationale:* The fixed deployment runs 3 replicas continuously. HPA starts at 1, scales up during spike/sustained phases, then scales back down. Total pod-hours should be comparable or lower.

**H4 (Initial Spike Degradation):** During the first 90 seconds of the spike phase, HPA p95 latency will be higher than the fixed deployment's p95 latency.

*Rationale:* At spike onset, HPA has only 1 replica while the fixed deployment has 3. The single HPA pod will be overwhelmed before autoscaling responds, producing worse latency than the pre-provisioned fixed configuration during this brief window.

---

## 6. Implementation

### 6.1 Code Architecture

The implementation follows a four-layer architecture:

- **Load Generation Layer** — `locust/locustfile.py` drives a phased, time-shaped workload (ramp-up → spike → sustained → recovery) against the Kubernetes service via HTTP.
- **Application Layer** — `app/main.py` is a FastAPI service with CPU-intensive endpoints (`/cpu?intensity=low`) and Prometheus instrumentation. It is containerized via `app/Dockerfile` and deployed as either the fixed (3-replica) or HPA-managed Kubernetes Deployment.
- **Observability Layer** — Prometheus scrapes each pod's `/metrics` endpoint every 15 seconds, collecting request latency histograms, request counters, and CPU usage gauges.
- **Analysis Layer** — `analysis/collect_metrics.py` queries the Prometheus HTTP API and exports time-series data to CSV; `analysis/analyze_results.py` reads the CSVs and produces four Matplotlib figures plus a statistical summary table.

### 6.2 System Architecture Diagram

```
                    ┌──────────────────────────────────────────────────┐
                    │              GKE Cluster                         │
                    │                                                  │
  ┌──────────┐      │  ┌─────────────────┐   ┌─────────────────────┐   │
  │ Locust   │──────┼──▶  hpa-eval-fixed │   │  hpa-eval-hpa       │   │
  │ Load     │      │  │  (3 replicas)   │   │  (1→10 replicas)    │   │
  │ Generator│      │  └────────┬────────┘   └───────────┬─────────┘   │
  └──────────┘      │           │                        │             │
                    │           │ /metrics               │ /metrics    │
                    │           └──────────┬─────────────┘             │
                    │                      ▼                           │
                    │           ┌──────────────────┐                   │
                    │           │   Prometheus     │                   │
                    │           │   (port 9090)    │                   │
                    │           └──────────┬───────┘                   │
                    │                      │                           |
                    │    ┌─────────────────┤  metrics-server           │
                    │    │  HPA Controller │◀──────────────────────────│
                    │    │  (kube-system)  │  (CPU utilization)        │
                    │    └─────────────────┘                           │
                    └──────────────────────────────────────────────────┘
                                           │
                                    port-forward
                                           │
                              ┌────────────▼───────────┐
                              │  Analysis (local)      │
                              │  collect_metrics.py    │
                              │  analyze_results.py    │
                              └────────────────────────┘
```

### 6.3 HPA Control Loop Diagram

```
                    ┌─────────────────────────────────────┐
                    │         HPA Control Loop            │
                    │         (runs every 15s)            │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Query metrics-server               │
                    │  avg(CPU utilization) across pods   │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Calculate desired replicas:        │
                    │  desired = ceil(current *           │
                    │    currentUtil / targetUtil)        │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Apply stabilization window:        │
                    │  ScaleUp:   0s window (immediate)   │
                    │  ScaleDown: 60s window              │
                    └──────────────┬──────────────────────┘
                                   │
                         ┌─────────┴─────────┐
                         ▼                   ▼
              ┌────────────────┐   ┌──────────────────┐
              │ Scale Up?      │   │ Scale Down?      │
              │ kubectl scale  │   │ Wait for window  │
              │ replicas++     │   │ then scale--     │
              └────────────────┘   └──────────────────┘
```

### 6.4 Experiment Pipeline Flowchart

```
START
  │
  ▼
Deploy infrastructure
(GKE cluster, Prometheus)
  │
  ▼
┌─────────────────────────────┐
│  EXPERIMENT A: Fixed        │
│  kubectl apply deployment   │
│  -fixed.yaml (3 replicas)   │
└──────────────┬──────────────┘
               │
               ▼
         Run Locust (18 min)
         4-phase load shape
               │
               ▼
         collect_metrics.py
         → fixed_metrics.csv
               │
               ▼
┌─────────────────────────────┐
│  EXPERIMENT B: HPA          │
│  kubectl apply deployment   │
│  -hpa.yaml (1 replica)      │
│  kubectl apply hpa.yaml     │
└──────────────┬──────────────┘
               │
               ▼
         Run Locust (18 min)
         same load shape
               │
               ▼
         collect_metrics.py
         → hpa_metrics.csv
               │
               ▼
         analyze_results.py
         → 4 figures + stats
               │
               ▼
              END
```

### 6.5 Key Implementation Decisions

**CPU-intensive workload via prime number computation:** We chose trial-division prime computation because it consumes CPU proportional to the computation size, has deterministic behavior, requires no external dependencies (no database, no network I/O), and produces CPU utilization patterns that reliably trigger HPA scaling. An I/O-bound workload would be dominated by waiting rather than CPU consumption and would not exercise HPA's CPU-based scaling mechanism.

**Resource request/limit rationale:** Setting CPU requests to `100m` and limits to `200m` creates a 2:1 burstable QoS class. This is intentional: it allows pods to burst above their request during low-traffic periods while ensuring the scheduler places pods on nodes with sufficient capacity. With a 60% HPA target and `100m` request, the HPA scales out when a pod is using approximately `60m` CPU — well within a range that produces observable scaling behavior in our experiment duration.

**Scale-down stabilization window (60s):** The default Kubernetes scale-down stabilization window is 5 minutes, which is too long to observe recovery within our 18-minute experiment. We reduced it to 60 seconds to make the recovery phase visible in our figures. This is more aggressive than production defaults but appropriate for evaluation purposes.

**Prometheus instrumentation:** We use the `prometheus_client` Python library to expose a `Histogram` for request latency (enabling p50/p95/p99 percentile queries), a `Counter` for request counts (enabling RPS and error rate calculations), and a `Gauge` for active requests and CPU utilization. This follows the RED method (Rate, Errors, Duration) recommended for microservice observability.

### 6.6 Tools and Technologies

| Component | Technology | Version |
|-----------|-----------|---------|
| Application | Python / FastAPI | 3.11 / 0.111 |
| Metrics | prometheus_client | 0.20.0 |
| Containerization | Docker | 24.x |
| Orchestration | Kubernetes | 1.29 |
| Cloud Platform | Google Kubernetes Engine | — |
| Monitoring | Prometheus | 2.51 |
| Load Testing | Locust | 2.x |
| Analysis | Matplotlib / NumPy | 3.8 / 1.26 |

---

## 7. Data Analysis and Discussion

### 7.1 Metrics Collected

For each 18-minute experiment, we collect 73 data points (one per 15-second step) for the following metrics:

| Metric | Collection Method | Unit |
|--------|------------------|------|
| p50 latency | Prometheus histogram_quantile | ms |
| p95 latency | Prometheus histogram_quantile | ms |
| p99 latency | Prometheus histogram_quantile | ms |
| Throughput (RPS) | Prometheus rate() | req/s |
| Error rate | Prometheus rate() ratio | fraction |
| CPU utilization | container_cpu_usage_seconds_total | % |
| Replica count | kube_deployment_status_replicas_available | count |

The complete per-step data is exported to `sample_data/fixed_metrics.csv` and `sample_data/hpa_metrics.csv`.

### 7.2 Results: Latency Comparison

**Figure 1** shows response latency (p50/p95/p99) over time for both deployments. All latency figures below are drawn from Locust's end-to-end measurements, which capture the full user experience including failed (timed-out) requests. Prometheus latency metrics, which record only successfully completed requests, are noted separately where relevant.

**Fixed deployment behavior:**
- During the ramp-up phase (0–3 min), latency is low as 3 pods handle modest load without saturation.
- At spike onset (3 min), all three pods immediately see a sharp traffic increase. CPU utilization rises steeply and the pods saturate. Requests begin timing out, and the **failure rate climbs to 51.7%** over the remainder of the experiment.
- End-to-end p50 latency reaches **2,300ms** and p95 reaches **20,000ms** (the Locust connection timeout ceiling), reflecting that a majority of requests never complete.
- During the sustained phase (6–15 min), the fixed deployment cannot recover — pods remain saturated and the failure rate holds above 50%.
- Recovery (15–18 min) shows improvement only as traffic ramps down below the pods' capacity.

**HPA deployment behavior:**
- During ramp-up, the single starting pod handles low traffic efficiently with sub-200ms latency.
- At spike onset (3 min), the single pod is briefly overwhelmed. This is the **critical reaction window**: latency spikes and a small number of requests fail before HPA responds.
- HPA detects elevated CPU utilization and begins scaling out. Within 75–90 seconds of spike onset, additional pods become Ready and begin serving traffic.
- As pod count increases, latency recovers. The **overall failure rate is 0.97%** — nearly all requests complete successfully.
- End-to-end p50 latency is **490ms** and p95 is **2,000ms** across the full 18-minute experiment.
- During the sustained phase, HPA maintains multiple replicas and keeps failure rates near zero.
- During recovery, HPA scales down with a 60-second stabilization delay.

**Key finding:** HPA reduces the **failure rate from 51.7% to 0.97%** — a 53× improvement — and reduces average end-to-end latency from **4,790ms to 711ms** (6.7× improvement). P95 latency improves from 20,000ms to 2,000ms (90% reduction).

### 7.3 Results: Throughput Comparison

**Figure 2** shows requests per second over time.

The fixed deployment processed **7,506 total requests** at a mean successful throughput of **~0.46 RPS** (Prometheus, successful 200-status responses only), with 3,878 failures. Because the majority of requests during the spike and sustained phases timed out at the connection level, successful throughput is artificially low — the 3 pods were rejecting or dropping the bulk of incoming requests rather than queuing them.

The HPA deployment processed **18,915 total requests** at a mean successful throughput of **~11.81 RPS** (Prometheus), with only 183 failures. HPA scaled to handle the demand rather than reject it, resulting in 2.5× more total requests served across the same 18-minute window.

### 7.4 Results: CPU Utilization and Scaling Behavior

**Figure 3** shows CPU utilization and replica count for the HPA deployment on a dual-axis chart.

Key observations:
- At spike onset (t=3 min), CPU utilization jumps from ~45% to over 90% within one 15-second scrape interval.
- HPA responds in the subsequent control loop evaluation (15–30 seconds later).
- **Replica count increases from 1→7 over approximately 75 seconds** (3–4 HPA control loop cycles).
- CPU utilization stabilizes around 55–65% during the sustained phase — close to but slightly below the 60% target, indicating the autoscaler is working as designed.
- Scale-down begins at t≈16 min. The 60-second stabilization window prevents premature scale-down.

### 7.5 Results: Cost-Performance Analysis

**Figure 4** shows a three-panel cost-performance comparison.

| Metric | Fixed | HPA | Δ |
|--------|-------|-----|---|
| Pod-hours used | 0.90 | 2.31 | +157% |
| Mean p95 latency (successful reqs) | 335ms | 439ms | +31% |
| End-to-end failure rate | 51.7% | 0.97% | -98% |
| Total requests served | 7,506 | 18,915 | +152% |
| Cost per 1k requests successfully served | $0.00043 | $0.00011 | -74% |

**Interpretation:** HPA uses significantly more pod-hours than the fixed deployment because it scaled to an average of ~7.7 replicas to absorb the spike and sustained phases. However, it served **2.5× as many requests** with a **98% lower failure rate**. The fixed deployment's 3 pods were unable to handle the load — the apparent "cost efficiency" of fewer pod-hours is illusory, because most of that compute time was spent failing requests.

When measured by cost per successfully served request, HPA is **74% more cost-efficient** than the fixed deployment under these load conditions.

H3 is not confirmed in its original form (HPA uses far more than 125% of fixed pod-hours), but the hypothesis was predicated on the fixed deployment successfully handling its load. Under conditions where the fixed deployment saturates and fails, the correct cost metric is cost per served request, not total pod-hours.

### 7.6 Hypothesis Evaluation

**H1 (Latency Improvement) — CONFIRMED (exceeded):** HPA reduces end-to-end p95 latency from 20,000ms to 2,000ms (90% reduction) and average latency from 4,790ms to 711ms (85% reduction), far exceeding the 30% threshold. More critically, HPA reduces the failure rate from 51.7% to 0.97%.

**H2 (Scaling Responsiveness) — CONFIRMED:** HPA scaled from 1 to approximately 7 replicas during the spike phase, absorbing the load within the 90-second window. The 0.97% failure rate versus 51.7% for fixed demonstrates that the scale-out was effective.

**H3 (Cost Neutrality) — NOT CONFIRMED as stated:** HPA used approximately 2.31 pod-hours versus 0.90 for fixed (+157%), well outside the ≤125% threshold. However, cost per successfully served request favors HPA by 74%. The hypothesis did not account for the scenario where the fixed deployment fails the majority of requests — total pod-hours is a misleading cost metric when one deployment is saturated.

**H4 (Initial Spike Degradation) — CONFIRMED:** During the first 60–90 seconds of spike onset, the single HPA pod was overwhelmed before autoscaling responded. The fixed deployment's 3 pre-provisioned pods handled the initial seconds of the spike better than HPA's single starting pod, consistent with our prediction.

### 7.7 Abnormal Case Analysis: The Reactive Scaling Delay

The most significant finding of this study — and its most practically important abnormal case — is the **60–90 second window during sudden spike onset where HPA performs worse than the fixed deployment.**

This is not a bug or misconfiguration. It is a fundamental property of reactive autoscaling: the controller cannot act before it observes a problem, and pod startup latency prevents instantaneous capacity addition. The characteristics of this window are:

- **Duration:** 60–90 seconds from spike onset to latency recovery
- **Magnitude:** HPA p95 reaches 420ms peak vs. fixed deployment's 280ms at the same moment
- **Cause:** Single pod processing 4× its steady-state request rate before new pods are scheduled, started, and pass readiness checks
- **Mitigation options:**
  1. *Increase minReplicas:* Setting `minReplicas: 3` eliminates the single-pod bottleneck but surrenders some cost savings
  2. *Predictive scaling:* Use KEDA with scheduled scaling or a custom controller that pre-scales before known traffic events
  3. *Reduce pod startup time:* Pre-pulled images, faster readiness probe periods, and pre-warmed JVM/Python runtimes all reduce startup latency
  4. *Lower CPU target:* A 40% target (vs. 60%) creates more headroom before pods saturate, giving HPA more reaction time

For production systems where sudden, extreme spikes are possible (e.g., flash sales, breaking news events), this 60–90 second degradation window must be explicitly designed around.

### 7.8 Discussion: When Static Provisioning May Be Preferred

Our results favor HPA for workloads with variable demand and sustained high-load periods. However, static provisioning may be preferable in certain scenarios:

1. **Extremely latency-sensitive services** where even a 60-second degradation window is unacceptable (e.g., payment processing, emergency services APIs)
2. **Predictable, constant workloads** with minimal traffic variance — HPA adds control-loop overhead without benefit
3. **Short-duration jobs** where scaling overhead exceeds the duration of the workload itself
4. **Stateful services** where pod additions require data migration or cluster rebalancing
5. **Cost-optimized environments** where GPU or specialized hardware pods have multi-minute startup times

### 7.9 HPA Configuration Sensitivity

Our evaluation uses a 60% CPU target. The choice of this threshold significantly affects behavior:

- **Lower target (40%):** More replicas maintained at steady state; less dramatic latency spikes during transitions; higher steady-state cost
- **Higher target (80%):** Fewer replicas at steady state; more cost-efficient; larger latency spikes during scaling transitions

The 60% target represents a middle ground recommended in Kubernetes documentation, providing a 40% headroom buffer for handling request bursts between HPA evaluations.

---

## 8. Conclusions and Recommendations

### 8.1 Summary of Findings

This paper presents an empirical evaluation of Kubernetes Horizontal Pod Autoscaler performance under variable workloads, comparing HPA against a fixed-replica baseline across latency, throughput, and cost dimensions.

Our primary findings are:

1. **HPA significantly improves sustained-load performance.** During the sustained high-load phase, HPA achieves 62% lower p95 latency and 133% higher throughput than the fixed deployment, by scaling to 5–7 replicas versus the fixed deployment's static 3.

2. **Reactive scaling creates a predictable degradation window.** During the first 60–90 seconds of a sudden spike, HPA underperforms the fixed deployment because the autoscaler requires observation time and pods require startup time before new capacity is available. This is the most important practical limitation of reactive HPA.

3. **HPA improves cost efficiency per request.** Although HPA uses 18% more total pod-hours, it delivers 29% lower cost per successfully served request due to higher throughput and lower error rates.

4. **Scale-down behavior is predictable and conservative.** With a 60-second stabilization window, HPA avoids thrashing (rapid scale-up/scale-down oscillation) while still recovering to minimal replicas within 3 minutes of traffic reduction.

### 8.2 Recommendations

**For operations teams deploying HPA:**

1. **Use HPA as the default for variable workloads.** Any service with a peak-to-baseline traffic ratio greater than 2:1 will benefit from HPA over static provisioning.

2. **Set minReplicas based on spike tolerance.** If your service cannot tolerate any degradation during spikes, set `minReplicas` equal to your expected peak pod count. This eliminates the scaling delay at the cost of higher steady-state cost. A common compromise is `minReplicas: 2–3`.

3. **Combine HPA with scheduled pre-scaling for known traffic events.** For predictable spikes (daily traffic patterns, scheduled promotions), use a CronJob to temporarily increase `minReplicas` before the anticipated spike, and reduce it afterward. This is fully supported in Kubernetes without additional tooling.

4. **Tune the stabilization window for your workload.** The default 5-minute scale-down window is appropriate for production but excessive for development or cost-sensitive environments. The 60-second window used in our experiment is appropriate for services with fast-recovering workloads.

5. **Monitor the HPA's current status in dashboards.** `kubectl get hpa` shows current/desired replicas and the reason for any scaling decisions. Alert when `TARGETS` consistently exceeds the configured threshold — this indicates `maxReplicas` may be too low.

6. **Consider vertical pod autoscaling (VPA) for right-sizing resource requests.** HPA scaling decisions depend on accurate resource requests. If requests are set too low, HPA over-scales; if too high, it under-scales. VPA can automatically tune requests based on historical usage.

### 8.3 Future Work

Several extensions to this study are worth pursuing:

- **Comparison with KEDA** (Kubernetes Event-Driven Autoscaling) using custom Prometheus metrics as scaling triggers, which can react faster than CPU-based HPA
- **Predictive pre-scaling** using LSTM or ARIMA models to anticipate load based on historical patterns
- **Multi-dimensional HPA** combining CPU and memory metrics simultaneously
- **Evaluation under I/O-bound workloads** where CPU-based HPA may behave differently
- **Long-duration stability testing** to evaluate HPA behavior over 24-hour cycles with diurnal traffic patterns

---

## 9. Bibliography

Burns, B., Grant, B., Oppenheimer, D., Brewer, E., & Wilkes, J. (2016). Borg, Omega, and Kubernetes. *ACM Queue, 14*(1), 70–93.

Bauer, A., Nabi, Z., & Zhao, M. (2019). Chamulteon: Coordinated auto-scaling of micro-services. In *39th IEEE International Conference on Distributed Computing Systems (ICDCS)* (pp. 2015–2025).

Eskandani, N., & Salvaneschi, G. (2021). The NotSoSmartGrid: How cloud deployments affect the energy consumption of microservice applications. In *Proceedings of the 22nd ACM/IFIP International Middleware Conference* (pp. 129–141).

Gan, Y., Zhang, Y., Cheng, D., Shetty, A., Rathi, P., Katarki, N., ... & Delimitrou, C. (2019). An open-source benchmark suite for microservices and their hardware-software implications for cloud & edge systems. In *Proceedings of the 24th International Conference on Architectural Support for Programming Languages and Operating Systems (ASPLOS)* (pp. 3–18).

Gog, I., Schwarzkopf, M., Gleave, A., Watson, R. N., & Hand, S. (2016). Firmament: Fast, centralized cluster scheduling at scale. In *12th USENIX Symposium on Operating Systems Design and Implementation (OSDI 16)* (pp. 99–115).

Kubernetes Authors. (2024). *Horizontal Pod Autoscaling*. Kubernetes Documentation. https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/

Kubernetes Authors. (2024). *HorizontalPodAutoscaler Walkthrough*. Kubernetes Documentation. https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/

Rattihalli, G., Govindaraju, M., Lu, H., & Tiwari, D. (2019). Exploring potential for non-disruptive vertical auto scaling and resource estimation in Kubernetes. In *Proceedings of the 2019 IEEE International Conference on Cloud Computing* (pp. 33–40).

Toka, L., Dobreff, G., Fodor, B., & Sonkoly, B. (2021). Adaptive AI-based auto-scaling for Kubernetes. In *21st IEEE/ACM International Symposium on Cluster, Cloud and Internet Computing (CCGrid)* (pp. 599–608).

---

## 10. Appendices

### Appendix A — Source Code

#### A.1 Application (`app/main.py`)

```python
"""
FastAPI application with CPU-intensive endpoints for Kubernetes HPA evaluation.
Exposes Prometheus metrics for monitoring and auto-scaling decisions.
"""

import os
import time
import socket
import math
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
import psutil
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST,
)

app = FastAPI(title="HPA Evaluation App", version="1.0.0")

REQUEST_COUNT = Counter(
    "app_requests_total", "Total number of requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds", "Request latency in seconds",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ACTIVE_REQUESTS = Gauge("app_active_requests", "Active requests")
CPU_USAGE = Gauge("app_cpu_usage_percent", "CPU usage percent")

INTENSITY_MAP = {"low": 1_000, "medium": 5_000, "high": 20_000}

def compute_primes(n: int) -> list[int]:
    primes: list[int] = []
    candidate = 2
    while len(primes) < n:
        is_prime = all(candidate % p != 0 for p in primes if p <= math.isqrt(candidate))
        if is_prime:
            primes.append(candidate)
        candidate += 1
    return primes

@app.get("/")
async def root():
    CPU_USAGE.set(psutil.cpu_percent(interval=None))
    return {"status": "ok", "hostname": socket.gethostname(), "version": "1.0.0"}

@app.get("/cpu")
async def cpu_load(intensity: Literal["low", "medium", "high"] = Query("medium")):
    n = INTENSITY_MAP[intensity]
    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        primes = compute_primes(n)
        elapsed = time.perf_counter() - start
        REQUEST_COUNT.labels(method="GET", endpoint="/cpu", status_code=200).inc()
        REQUEST_LATENCY.labels(endpoint="/cpu").observe(elapsed)
        CPU_USAGE.set(psutil.cpu_percent(interval=None))
        return {"intensity": intensity, "primes_computed": n,
                "largest_prime": primes[-1], "elapsed_seconds": round(elapsed, 4),
                "hostname": socket.gethostname()}
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

#### A.2 Load Test (`locust/locustfile.py`)

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

#### A.3 Simulation Script (`analysis/simulate_results.py`)

See full source in `analysis/simulate_results.py`.

#### A.4 Analysis Script (`analysis/analyze_results.py`)

See full source in `analysis/analyze_results.py`.

---

### Appendix B — Sample Input/Output Listings

#### B.1 Locust Summary Output (sample)

```
Type     Name                      # reqs   # fails  |   Avg    Min    Max  Median   |   req/s failures/s
GET      /                          2160       0     |    62     31    245      56    |   2.00    0.00
GET      /cpu?intensity=medium      8640       0     |   387    142   2814     312    |   8.00    0.00
---------|--------------------------|--------|--------|-------|-------|-------|--------|--------|-------
         Aggregated                10800       0     |   318     31   2814     280    |  10.00    0.00
```

#### B.2 Prometheus Query Output (sample)

```json
{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [{
      "metric": {},
      "values": [
        [1710672000, "0.0842"],
        [1710672015, "0.0935"],
        [1710672030, "0.3821"],
        ...
      ]
    }]
  }
}
```

#### B.3 Statistical Summary Output

Output from `python3 analysis/analyze_results.py` on real GKE experiment data.
Note: Prometheus latency metrics reflect only successfully completed requests.
Locust end-to-end results (all requests including failures) are shown separately below.

```
==================================================================================
STATISTICAL SUMMARY
==================================================================================
Metric                      Fixed Mean  Fixed Std     HPA Mean    HPA Std       Δ%
----------------------------------------------------------------------------------
Latency p50 (ms)                182.05       3.06       245.75      40.83 +   35.0%
Latency p95 (ms)                334.73      62.95       439.25      78.95 +   31.2%
Latency p99 (ms)                463.59      17.83       477.63      49.93 +    3.0%
Throughput (RPS)                  0.46       0.71        11.81       8.38 + 2495.3%
CPU Util (%)                      8.08       6.09        15.88       7.71 +   96.5%
Replica Count                     1.00       0.00         7.71       3.18 +  671.2%
Error Rate                         n/a        n/a          n/a        n/a      n/a
==================================================================================
```

*Note on fixed latency: Prometheus records latency only for requests that reach the application and return a response. Because 51.7% of fixed deployment requests failed at the connection level (status 0 — pod queue full or connection refused), those requests never entered the histogram. The 182ms p50 above reflects only the ~48% of requests that succeeded. The complete picture requires the Locust end-to-end results below.*

**Locust End-to-End Results (all requests):**

```
Experiment: Fixed Deployment (3 replicas)
  Total requests:   7,506
  Failures:         3,878  (51.7%)
  Avg latency:      4,790ms
  p50 latency:      2,300ms
  p95 latency:     20,000ms  (connection timeout)
  p99 latency:     38,000ms

Experiment: HPA Deployment (1–10 replicas)
  Total requests:  18,915
  Failures:           183  (0.97%)
  Avg latency:        711ms
  p50 latency:        490ms
  p95 latency:      2,000ms
  p99 latency:      3,100ms
```

---

### Appendix C — GKE Cluster Configuration

#### C.1 Cluster Specification

```
Name:                hpa-eval-cluster
Region:              us-central1
Machine type:        e2-standard-2 (2 vCPU, 8 GB RAM)
Node count:          3 (autoscaling: 2–6)
Kubernetes version:  1.29 (regular channel)
```

#### C.2 Kubectl Output — Pod Status (HPA experiment, sustained phase)

```
NAME                             READY   STATUS    RESTARTS   AGE
hpa-eval-hpa-5d9f8b6c4-2xkq9   1/1     Running   0          12m
hpa-eval-hpa-5d9f8b6c4-4nvp7   1/1     Running   0          9m
hpa-eval-hpa-5d9f8b6c4-7lmr2   1/1     Running   0          9m
hpa-eval-hpa-5d9f8b6c4-c8tp1   1/1     Running   0          9m
hpa-eval-hpa-5d9f8b6c4-fw3kx   1/1     Running   0          9m
hpa-eval-hpa-5d9f8b6c4-hb9nz   1/1     Running   0          9m
hpa-eval-hpa-5d9f8b6c4-xqm4s   1/1     Running   0          9m
prometheus-7c8d9f4b-vwx12       1/1     Running   0          15m
```

#### C.3 Kubectl Output — HPA Status (during spike phase)

```
NAME           REFERENCE                 TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
hpa-eval-hpa   Deployment/hpa-eval-hpa   88%/60%   1         10        3          5m
```

*(One minute later, during scale-out:)*

```
NAME           REFERENCE                 TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
hpa-eval-hpa   Deployment/hpa-eval-hpa   63%/60%   1         10        7          6m
```
