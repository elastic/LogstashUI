# Testing & Validation

The **Test SNMP** modal lets you validate your configuration against real devices before deploying anything.

> [!NOTE]
> There is no built-in device simulator — all testing runs live SNMP queries against real, reachable devices. Nothing in the test modal changes your staged configuration or deployed pipelines.

## Test Profile Against Device

Validates that a profile actually collects data from a device.

1. Open the **Test SNMP** modal and stay on the first tab.
2. Select a device and the template or profile to test.
3. Run the test — LogstashUI executes the profile's GET/table queries against the device using its configured credential.
4. Review the results: each OID with its returned value and the field it maps to.

Use this to answer "will this template produce data on this hardware?" before you deploy — missing values usually mean the device doesn't implement that OID (wrong vendor profile) or the credential lacks access to that subtree.

## Walk Device

Explores everything a device exposes over SNMP.

1. Switch to the **Walk Device** tab.
2. Enter host, port, credential, and a start OID (use `.1` or leave the default to walk everything).
3. Run the walk — results appear as an OID → value table, which you can copy out.

A walk is the raw material for profile building: it shows every OID the device actually supports, including vendor enterprise subtrees.

## Generate Template and Profiles (AI)

Once a walk completes, a **Generate Template and Profiles** button appears. It opens the AI template generator pre-filled with the walk output:

1. Choose the Elasticsearch connection and AI model to use.
2. The walk output is uploaded to a temporary index, and the AI agent analyzes it — checking existing official profiles first so it reuses established field names and doesn't reinvent standard MIB coverage.
3. It proposes a device template plus profiles (GET/table OID mappings and normalizers) as JSON.
4. Review and accept — accepted profiles and the template are saved as **custom** entries you can edit, assign to devices, and deploy like any other.

You can also open the AI generator directly from the Device Templates page and paste in an snmpwalk you captured outside LogstashUI (see [Device Support](/docs/docs/logstashui/SNMP/device_support.md) for the recommended snmpwalk command).

---

## Related Documentation

- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Profiles and templates in depth
- **[Device Support](/docs/docs/logstashui/SNMP/device_support.md)** - Getting support for unrecognized devices
- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Field naming conventions to follow in custom profiles
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
