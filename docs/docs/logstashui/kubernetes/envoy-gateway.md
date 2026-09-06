# Envoy Gateway

Keep LogstashUI on HTTPS `:8443`. The HTTPRoute must send **HTTPS** to the pod and **skip verification** of the product self-signed leaf.

Envoy Gateway documents that skip on the **`Backend` CR**, not on `BackendTrafficPolicy`. `BackendTrafficPolicy` is retries, timeouts, and circuit breaking. `tls.insecureSkipVerify` exists only on `Backend`.

The Backend API is **disabled by default**. Enable it, then apply a `Backend` + `HTTPRoute`.

---

## 1. Enable the Backend API

Helm values:

```yaml
config:
  envoyGateway:
    extensionApis:
      enableBackend: true
```

Upgrade:

```bash
helm upgrade eg oci://docker.io/envoyproxy/gateway-helm \
  -n envoy-gateway-system \
  --reuse-values \
  --set config.envoyGateway.extensionApis.enableBackend=true
```

If you manage an `EnvoyGateway` config ConfigMap instead of Helm values, merge:

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyGateway
gateway:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
extensionApis:
  enableBackend: true
```

Restart the Envoy Gateway controller after the change. Confirm the `Backend` CRD is served:

```bash
kubectl api-resources | grep -i backend
```

---

## 2. HTTPRoute + Backend

The HTTPRoute `backendRefs` must use `group: gateway.envoyproxy.io` and `kind: Backend`. Point the `Backend` at the LogstashUI Service FQDN on port **8443**.

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: Backend
metadata:
  name: logstashui
  namespace: logstashui
spec:
  endpoints:
    - fqdn:
        hostname: logstashui.logstashui.svc.cluster.local
        port: 8443
  tls:
    insecureSkipVerify: true
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: logstashui
  namespace: logstashui
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: public          # your Gateway
      namespace: envoygw    # Gateway namespace
  hostnames:
    - logstashui.example.com
  rules:
    - backendRefs:
        - group: gateway.envoyproxy.io
          kind: Backend
          name: logstashui
      matches:
        - path:
            type: PathPrefix
            value: /
```

Skip-verify is for **testing / product-CA backends**. Prefer a `BackendTLSPolicy` with the product CA in production.

---

## 3. Gateway `allowedRoutes`

If the Gateway is in another namespace, its listener must allow HTTPRoutes from `logstashui`:

```yaml
allowedRoutes:
  namespaces:
    from: All
```

or a label selector that includes the `logstashui` namespace.

---

## 4. LogstashUI env

Do **not** set `LOGSTASHUI_TLS=false`. Set `CSRF_TRUSTED_ORIGINS=https://<hostname>` and `ALLOWED_HOSTS` to the same host. See [Kubernetes](index.md).
