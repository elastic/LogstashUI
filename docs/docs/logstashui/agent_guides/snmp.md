# SNMP monitoring

LogstashUI turns SNMP objects into Logstash pipelines for polling, traps, and discovery.

## Objects

- **Credential**: SNMP v1, v2c, or v3 auth. Secret values are never returned by the API.
- **Network**: a CIDR range. Its `deployment_mode` decides where polling runs (`CENTRALIZED` or `AGENT`) and `credential_mode` how credentials reach Logstash.
- **Device**: one host to poll (`ip_address` or `hostname`), linked to a `credential`, a `network`, and a `device_template`.
- **Profile**: a set of OIDs to poll. Official profiles ship with LogstashUI.
- **Template**: a device type that bundles profiles. Official templates are read-only.

## Adding a device

1. `snmp_credentials_list` to reuse a credential. Create one only if the user gives the details; never invent secrets.
2. `snmp_networks_list` to find the network the device belongs to.
3. `snmp_templates_list` with `search` to find a template for the vendor or model, and confirm the choice with the user.
4. `snmp_devices_create` with the host and the `credential`, `network`, and `device_template` IDs.
5. Follow the deploy steps: `snmp_deploy_diff`, show the plan, then `snmp_deploy_apply` after the user confirms.

## Profile format

`snmp_profiles_get` returns `profile_data` and `normalizers`; official profiles return the OIDs they ship with. To create or update a custom profile, send the same shape:

```json
{
  "profile_data": {
    "get": {"ups.battery.voltage": "1.3.6.1.2.1.33.1.2.5.0"},
    "walk": {},
    "table": {
      "interface": {
        "columns": {
          "index": "1.3.6.1.2.1.2.2.1.1",
          "name": "1.3.6.1.2.1.31.1.1.1.1",
          "traffic.in.bytes": "1.3.6.1.2.1.31.1.1.1.6"
        }
      }
    }
  },
  "normalizers": [
    {"operation": "multiply",
     "target": {"scope": "get", "field": "ups.battery.voltage"},
     "params": {"multiply_value": 0.1}}
  ]
}
```

- `get`: scalar OIDs, usually ending in `.0`. `walk`: a flat indexed subtree. `table`: per-row data (interfaces, sensors, filesystems) with named `columns`; a table name plus a column key form the field name (`interface.traffic.in.bytes`).
- Field names are lowercase dotted names with the unit kept (`.bytes`, `.pct`), never raw MIB object names like `ifHCInOctets`.
- `normalizers` convert units or derive values. Unknown operations, unknown params, wrong param types, and missing required params are rejected with a 400 that names the normalizer index. `multiply` scales `target.field` (`params.multiply_value`, optional `output_field`; otherwise it overwrites the field). `translate` maps raw values on `target.field` to strings (`params.mapping`, an object such as `{"1": "up"}`). `average` (table only) writes the average of `target.field` across rows to `params.output_field` (optional `multiply_value`). `sum` (get only) adds `params.input_fields` (a list) into `params.output_field`. `ratio` derives totals and percentages from two fields (`params.value1_field`, `value2_field`, and any of `total_output_field`, `ratio1_output_field`, `ratio2_output_field`, `complement_ratio_output_field`, `divide_output_field`). For a table, use `"target": {"scope": "table", "table": "<table>"}` and refer to fields as `<table>.<column>`.
- Never guess vendor OIDs (`1.3.6.1.4.1.<vendor>`). If you aren't sure an OID is right, tell the user to confirm it with `snmpwalk` first. Official profiles are read-only.

## Checking state

`snmp_deploy_status` says whether there are undeployed changes. Generated SNMP pipelines show up in `pipelines_list` with `managed_by: snmp`; don't edit them directly.

A network's discovery pipeline probes every address in its range except the ones that already belong to devices. So adding a device removes its address from the discovery diff, and deleting a device adds it back.
