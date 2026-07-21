# Device Support

Can't find an official template or profile for your hardware? You have three options — and one of them helps everyone else too.

## 1. Build a Custom Profile

Create your own [profile and device template](/docs/docs/logstashui/SNMP/configuration.md#profiles) with the OIDs your device exposes. Reuse the field names from the [SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md) so your data lines up with official profiles.

## 2. Generate One from a Walk

Run a walk from the [Test SNMP modal](/docs/docs/logstashui/SNMP/testing.md) and click **Generate Template and Profiles** — the AI generator drafts a template and profiles from what your device actually exposes, and you review before saving.

## 3. Send Us an snmpwalk

If you'd like your device supported **officially**, capture a full walk and send it to us — that's all we need to build and test a profile:

```bash
snmpwalk -ObentU -v2c -c public 192.168.1.1 .1 > device.snmpwalk
```

Replace `public` with your (read-only) community string and `192.168.1.1` with the device's address. The flags matter: `-ObentU` outputs numeric, untranslated OIDs and values, which is exactly the form profiles are built from.

Then [open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md) with the `device.snmpwalk` file attached, along with the device's vendor and model.

> [!WARNING]
> Review the walk file before sharing. sysContact, sysLocation, sysName, ARP/MAC tables, and similar OIDs can contain names, addresses, and internal network details you may want to redact.

## Sharing Your Profiles

Built a custom profile or template that works well? We'd love to make it official. Open an issue with the profile JSON (copy it from the profile modal) plus the device vendor/model it targets, and ideally the snmpwalk it was built from.

---

## Related Documentation

- **[Testing & Validation](/docs/docs/logstashui/SNMP/testing.md)** - Walk devices and AI-generate profiles from the UI
- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Custom profiles and templates
- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Field naming conventions
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
