# Deployment Recommendations

This is a sizing guide for the LogstashUI control plane (agent management,
network-device management, and pipeline simulation). It is not a sizing guide
for Logstash nodes processing production events.

**Recommended starting host:** 8 GB RAM and 4 vCPUs, including embedded mode
with local pipeline simulation.

## How many agents can one instance of LogstashUI handle?

Performance tests below used an Ubuntu VM with **8 GB RAM and 4 vCPUs**.
Agents check in every 60 seconds by default. All measured responses succeeded.

### Performance test results

| Type | Throughput | Average | Median | p95 | p99 | Slowest |
|------|------------|---------|--------|-----|-----|---------|
| Docker Compose (SQLite) | 130 check-ins/s | 27 ms | 25 ms | 44 ms | 66 ms | 139 ms |
| systemd (PostgreSQL) | 130 check-ins/s | 22 ms | 17 ms | 49 ms | 87 ms | 274 ms |

The systemd row used a second Ubuntu VM for PostgreSQL: **2 GB RAM and 2 vCPUs**,
default PostgreSQL configuration.

1,500 connected agents at the default 60-second interval is only about
**25 check-ins/s**. The 130 check-ins/s result is several thousand agents of
check-in headroom — well beyond the 1,500 we exercised for UI comfort. If you
need more than 1,500, please reach out — we would like to understand the use
case.

You can run LogstashUI on a host smaller than the recommendation above, but we
do not test or validate under that size.
