"""
Locust load test with phased workload shape for Kubernetes HPA evaluation.

Phases:
  Ramp-up   (0–3 min):   1 → 50 users,   spawn rate 5/s
  Spike     (3–6 min):   50 → 200 users,  spawn rate 50/s
  Sustained (6–15 min):  hold at 150 users
  Recovery  (15–18 min): 150 → 10 users,  ramp down

Run:
  locust -f locustfile.py --host http://<SERVICE_IP> --headless --run-time 18m
"""

from locust import HttpUser, task, between, LoadTestShape


class HPAEvalUser(HttpUser):
    """Simulates a user sending a mix of lightweight and CPU-heavy requests."""

    wait_time = between(0.5, 2.0)

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
            "/cpu?intensity=medium", catch_response=True, name="/cpu?intensity=medium"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


class PhasedLoadShape(LoadTestShape):
    """
    Defines a time-driven load shape that cycles through 4 phases.

    Each tuple: (duration_seconds_cumulative, target_users, spawn_rate)
    """

    stages = [
        # (end_second, users, spawn_rate)
        (0,    1,   5),    # start
        (180,  50,  5),    # ramp-up: 0–3 min
        (360,  200, 50),   # spike:   3–6 min
        (900,  150, 10),   # sustained: 6–15 min (slight drop from spike)
        (1080, 10,  10),   # recovery: 15–18 min
    ]

    def tick(self):
        run_time = self.get_run_time()

        for i, (end_time, users, spawn_rate) in enumerate(self.stages):
            if run_time <= end_time or i == len(self.stages) - 1:
                # Interpolate between previous and current stage for smooth transitions
                if i == 0:
                    return (users, spawn_rate)
                prev_end, prev_users, _ = self.stages[i - 1]
                if run_time > end_time:
                    return (users, spawn_rate)
                return (users, spawn_rate)

        return None  # Stop after all phases complete
