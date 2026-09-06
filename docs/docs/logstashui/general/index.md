# General

General guides for deploying, building, and maintaining LogstashUI.

---

## **[Deploying LogstashUI](/docs/docs/logstashui/general/deploy.md)**

All the ways to deploy LogstashUI.

**Covers:**
- Standard Docker deployment (recommended)
- Host-backed simulation
- pip / uv + systemd
- Kubernetes (see also the [Kubernetes](/docs/docs/logstashui/kubernetes/index.md) subsection)
- Air-gapped freeze (optional offline zips)
- Source development setup

**📖 [View deployment guide →](/docs/docs/logstashui/general/deploy.md)**

---

## **[Air-gapped freeze](/docs/docs/logstashui/general/offline.md)**

Optional connected-builder script that freezes LogstashUI plus `[databases]` and `[otel]` into zips for hosts with no PyPI or registry. Default `uv build` is unchanged.

**📖 [View air-gapped freeze →](/docs/docs/logstashui/general/offline.md)**

---

## **[Building from Source](/docs/docs/logstashui/general/build.md)**

Instructions for building and running LogstashUI from source.

**Covers:**
- Local development setup and prerequisites
- Running the development server
- Building the Docker image locally

**📖 [View build guide →](/docs/docs/logstashui/general/build.md)**

---

## **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)**

Keep LogstashUI up to date with the latest features and fixes.

**How to update:**
- LogstashUI notifies you when updates are available
- Simple one-command update process
- Works on both Windows and Linux

**📖 [View update guide →](/docs/docs/logstashui/general/updating.md)**

---

## Quick Links

- **[Getting Started](/docs/docs/getting_started.md)** - Initial setup and first steps
- **[Configuration](/docs/docs/logstashui/configuration/index.md)** - Configure LogstashUI settings
- **[LogstashUI Overview](/docs/docs/logstashui/index.md)** - Feature overview and introduction
