# Logstash Version Compatibility

It's very frequently asked if we can support 7.x and 8.x versions of Logstash. In most cases, those versions will work. We DO NOT test against those versions. You may, see plugin options that don't exist in earlier versions, and that's something you'll want to look out for.

## Compatibility Matrix

| LogstashUI Version | Logstash Version |
|--------------------|------------------|
| 0.4.x              | Logstash 9.3.x   |
| 0.5.x              | Logstash 9.4.x   |


## Version Support

### Logstash 9.x (Primary Focus)

LogstashUI's primary focus is compatibility with **Logstash version 9**. We strongly recommend upgrading to version 9 to take full advantage of all features and capabilities.

- **Best supported version:** 9.3
- Full feature support in the pipeline editor
- All configuration options available
- Optimal performance and stability



## Upgrading to Version 9

We strongly urge all users to work toward upgrading to Logstash version 9 for the best experience with LogstashUI.

### Need Help Upgrading?

If you have specific requirements or constraints that prevent you from upgrading to version 9, please reach out to us.

## Configuration Compatibility Notes

When using LogstashUI with different Logstash versions, be aware that:

- The pipeline editor may display configuration options that are not available in your specific Logstash version
- Features introduced in newer versions of Logstash may not function on older versions
- Always verify that pipeline configurations are compatible with your deployed Logstash version before production use

## Getting Support

If you encounter compatibility issues or have questions about version support, please contact us for assistance.
