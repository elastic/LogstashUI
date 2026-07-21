# Updating

LogstashUI will notify you when a new version is available via a banner in the navigation sidebar.

To update LogstashUI to the latest version:

> [!WARNING]
> `--update` switches the repository to the `main` branch (`git checkout main`) before pulling. If you are running from a feature branch or have local modifications, note that you will be moved off your branch.

## Linux

```bash
cd LogstashUI/bin
./start_logstashui.sh --update
```

## Windows

```cmd
cd LogstashUI\bin
start_logstashui.bat --update
```

---

## Related Documentation

- **[Building and Running](/docs/docs/logstashui/general/build.md)** - Build and deployment guides
- **[Configuration](/docs/docs/logstashui/configuration/index.md)** - Configure LogstashUI settings
- **[General Overview](/docs/docs/logstashui/general/index.md)** - Return to general guides index
