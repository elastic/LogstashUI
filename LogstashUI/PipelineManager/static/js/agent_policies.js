//Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
//or more contributor license agreements. Licensed under the Elastic License;
//you may not use this file except in compliance with the Elastic License.

document.addEventListener('DOMContentLoaded', function() {
    let editor = null;
    let currentFile = 'logstash.yml';
    let currentMode = 'form'; // 'form' or 'code'
    let currentPolicy = 'default';
    let customPolicies = []; // Store custom policy names
    
    // Make currentFile globally accessible for save function
    window.policyCurrentFile = currentFile;
    
    // Default file contents
    const fileContents = {
        'logstash.yml': `# Settings file in YAML
#
# Settings can be specified either in hierarchical form, e.g.:
#
#   pipeline:
#     batch:
#       size: 125
#       delay: 5
#
# Or as flat keys:
#
#   pipeline.batch.size: 125
#   pipeline.batch.delay: 5
#
# ------------  Node identity ------------
#
# Use a descriptive name for the node:
#
# node.name: test
#
# If omitted the node name will default to the machine's host name
#
# ------------ Data path ------------------
#
# Which directory should be used by logstash and its plugins
# for any persistent needs. Defaults to LOGSTASH_HOME/data
#
# path.data:
#
# ------------ Pipeline Settings --------------
#
# The ID of the pipeline.
#
# pipeline.id: main
#
# Set the number of workers that will, in parallel, execute the filters+outputs
# stage of the pipeline.
#
# This defaults to the number of the host's CPU cores.
#
# pipeline.workers: 2
#
# How many events to retrieve from inputs before sending to filters+workers
#
# pipeline.batch.size: 125
#
# How long to wait in milliseconds while polling for the next event
# before dispatching an undersized batch to filters+outputs
#
# pipeline.batch.delay: 50
#
# Controls when output batches are split into smaller chunks. When the event count of a batch
# increases by this multiplication factor by the end of the pipeline's filter section, it is
# chunked based on the value of \`pipeline.batch.size\`. For example: a batch size of 50 that grows
# to over 50,000 events (1000x50=50,000) will be sent to outputs 50 events at a time instead of a
# single enormous batch. Useful when batch size grows unpredictably due to filter plugins such
# as split or clone.
# Default is 1000 (effectively disabled). Set to a lower value to enable chunking.
#
# pipeline.batch.output_chunking.growth_threshold_factor: 1000
#
# Set the pipeline's batch metrics reporting mode. It can be "disabled" to disable it.
# "minimal" to collect only 1% of the batches metrics, "full" to collect all batches.
# Default is "minimal".
#
# pipeline.batch.metrics.sampling_mode: "minimal"
#
# Force Logstash to exit during shutdown even if there are still inflight
# events in memory. By default, logstash will refuse to quit until all
# received events have been pushed to the outputs.
#
# WARNING: Enabling this can lead to data loss during shutdown
#
# pipeline.unsafe_shutdown: false
#
# Set the pipeline event ordering. Options are "auto" (the default), "true" or "false".
# "auto" automatically enables ordering if the 'pipeline.workers' setting
# is also set to '1', and disables otherwise.
# "true" enforces ordering on the pipeline and prevent logstash from starting
# if there are multiple workers.
# "false" disables any extra processing necessary for preserving ordering.
#
# pipeline.ordered: auto
#
# Sets the pipeline's default value for \`ecs_compatibility\`, a setting that is
# available to plugins that implement an ECS Compatibility mode for use with
# the Elastic Common Schema.
# Possible values are:
# - disabled
# - v1
# - v8 (default)
# Pipelines defined before Logstash 8 operated without ECS in mind. To ensure a
# migrated pipeline continues to operate as it did before your upgrade, opt-OUT
# of ECS for the individual pipeline in its \`pipelines.yml\` definition. Setting
# it here will set the default for _all_ pipelines, including new ones.
#
# pipeline.ecs_compatibility: v8
#
# ------------ Pipeline Configuration Settings --------------
#
# Where to fetch the pipeline configuration for the main pipeline
#
# path.config:
#
# Pipeline configuration string for the main pipeline
#
# config.string:
#
# At startup, test if the configuration is valid and exit (dry run)
#
# config.test_and_exit: false
#
# Periodically check if the configuration has changed and reload the pipeline
# This can also be triggered manually through the SIGHUP signal
#
# config.reload.automatic: false
#
# How often to check if the pipeline configuration has changed (in seconds)
# Note that the unit value (s) is required. Values without a qualifier (e.g. 60)
# are treated as nanoseconds.
# Setting the interval this way is not recommended and might change in later versions.
#
# config.reload.interval: 3s
#
# Show fully compiled configuration as debug log message
# NOTE: --log.level must be 'debug'
#
# config.debug: false
#
# When enabled, process escaped characters such as \\n and \\" in strings in the
# pipeline configuration files.
#
# config.support_escapes: false
#
# ------------ API Settings -------------
# Define settings related to the HTTP API here.
#
# The HTTP API is enabled by default. It can be disabled, but features that rely
# on it will not work as intended.
#
# api.enabled: true
#
# By default, the HTTP API is not secured and is therefore bound to only the
# host's loopback interface, ensuring that it is not accessible to the rest of
# the network.
# When secured with SSL and Basic Auth, the API is bound to _all_ interfaces
# unless configured otherwise.
#
# api.http.host: 127.0.0.1
#
# The HTTP API web server will listen on an available port from the given range.
# Values can be specified as a single port (e.g., \`9600\`), or an inclusive range
# of ports (e.g., \`9600-9700\`).
#
# api.http.port: 9600-9700
#
# The HTTP API includes a customizable "environment" value in its response,
# which can be configured here.
#
# api.environment: "production"
#
# The HTTP API can be secured with SSL (TLS). To do so, you will need to provide
# the path to a password-protected keystore in p12 or jks format, along with credentials.
#
# api.ssl.enabled: false
# api.ssl.keystore.path: /path/to/keystore.jks
# api.ssl.keystore.password: "y0uRp4$$w0rD"
#
# The availability of SSL/TLS protocols depends on the JVM version. Certain protocols are
# disabled by default and need to be enabled manually by changing \`jdk.tls.disabledAlgorithms\` 
# in the $JDK_HOME/conf/security/java.security configuration file.
#
# api.ssl.supported_protocols: [TLSv1.2,TLSv1.3]
#
# The HTTP API can be configured to require authentication. Acceptable values are
#  - \`none\`:  no auth is required (default)
#  - \`basic\`: clients must authenticate with HTTP Basic auth, as configured
#             with \`api.auth.basic.*\` options below
# api.auth.type: none
#
# When configured with \`api.auth.type\` \`basic\`, you must provide the credentials
# that requests will be validated against. Usage of Environment or Keystore
# variable replacements is encouraged (such as the value \`"\${HTTP_PASS}"\`, which
# resolves to the value stored in the keystore's \`HTTP_PASS\` variable if present
# or the same variable from the environment)
#
# api.auth.basic.username: "logstash-user"
# api.auth.basic.password: "s3cUreP4$$w0rD"
#
# When setting \`api.auth.basic.password\`, the password should meet
# the default password policy requirements.
# The default password policy requires non-empty minimum 8 char string that
# includes a digit, upper case letter and lower case letter.
# Policy mode sets Logstash to WARN or ERROR when HTTP authentication password doesn't
# meet the password policy requirements.
# The default is WARN. Setting to ERROR enforces stronger passwords (recommended).
#
# api.auth.basic.password_policy.mode: WARN
#
# ------------ Queuing Settings --------------
#
# Internal queuing model, "memory" for legacy in-memory based queuing and
# "persisted" for disk-based acked queueing. Defaults is memory
#
# queue.type: memory
#
# If \`queue.type: persisted\`, the directory path where the pipeline data files will be stored.
# Each pipeline will group its PQ files in a subdirectory matching its \`pipeline.id\`.
# Default is path.data/queue.
#
# path.queue:
#
# If using queue.type: persisted, the page data files size. The queue data consists of
# append-only data files separated into pages. Default is 64mb
#
# queue.page_capacity: 64mb
#
# If using queue.type: persisted, the maximum number of unread events in the queue.
# Default is 0 (unlimited)
#
# queue.max_events: 0
#
# If using queue.type: persisted, the total capacity of the queue in number of bytes.
# If you would like more unacked events to be buffered in Logstash, you can increase the
# capacity using this setting. Please make sure your disk drive has capacity greater than
# the size specified here. If both max_bytes and max_events are specified, Logstash will pick
# whichever criteria is reached first
# Default is 1024mb or 1gb
#
# queue.max_bytes: 1024mb
#
# If using queue.type: persisted, the maximum number of acked events before forcing a checkpoint
# Default is 1024, 0 for unlimited
#
# queue.checkpoint.acks: 1024
#
# If using queue.type: persisted, the maximum number of written events before forcing a checkpoint
# Default is 1024, 0 for unlimited
#
# queue.checkpoint.writes: 1024
#
# If using queue.type: persisted, the compression goal. Valid values are \`none\`, \`speed\`, \`balanced\`, and \`size\`.
# The default \`none\` is able to decompress previously-written events, even if they were compressed.
#
# queue.compression: none
#
# ------------ Dead-Letter Queue Settings --------------
# Flag to turn on dead-letter queue.
#
# dead_letter_queue.enable: false

# If using dead_letter_queue.enable: true, the maximum size of each dead letter queue. Entries
# will be dropped if they would increase the size of the dead letter queue beyond this setting.
# Default is 1024mb
# dead_letter_queue.max_bytes: 1024mb

# If using dead_letter_queue.enable: true, the interval in milliseconds where if no further events eligible for the DLQ
# have been created, a dead letter queue file will be written. A low value here will mean that more, smaller, queue files
# may be written, while a larger value will introduce more latency between items being "written" to the dead letter queue, and
# being available to be read by the dead_letter_queue input when items are written infrequently.
# Default is 5000.
#
# dead_letter_queue.flush_interval: 5000

# If using dead_letter_queue.enable: true, controls which entries should be dropped to avoid exceeding the size limit.
# Set the value to \`drop_newer\` (default) to stop accepting new events that would push the DLQ size over the limit.
# Set the value to \`drop_older\` to remove queue pages containing the oldest events to make space for new ones.
#
# dead_letter_queue.storage_policy: drop_newer

# If using dead_letter_queue.enable: true, the interval that events have to be considered valid. After the interval has
# expired the events could be automatically deleted from the DLQ.
# The interval could be expressed in days, hours, minutes or seconds, using as postfix notation like 5d,
# to represent a five days interval.
# The available units are respectively d, h, m, s for day, hours, minutes and seconds.
# If not specified then the DLQ doesn't use any age policy for cleaning events.
#
# dead_letter_queue.retain.age: 1d

# If using dead_letter_queue.enable: true, the directory path where the data files will be stored.
# Default is path.data/dead_letter_queue
#
# path.dead_letter_queue:
#
# ------------ Debugging Settings --------------
#
# Options for log.level:
#   * fatal
#   * error
#   * warn
#   * info (default)
#   * debug
#   * trace
# log.level: info
#
# Options for log.format:
#   * plain (default)
#   * json
#
# log.format: plain
# log.format.json.fix_duplicate_message_fields: true
#
# path.logs:
#
# ------------ Other Settings --------------
#
# Allow or block running Logstash as superuser (default: false). Windows are excluded from the checking
# allow_superuser: false
#
# Where to find custom plugins
# path.plugins: []
#
# Flag to output log lines of each pipeline in its separate log file. Each log filename contains the pipeline.name
# Default is false
# pipeline.separate_logs: false
#
# Determine where to allocate memory buffers, for plugins that leverage them.
# Defaults to heap,but can be switched to direct if you prefer using direct memory space instead.
# pipeline.buffer.type: heap
#
# ------------ X-Pack Settings (not applicable for OSS build)--------------
#
# X-Pack Monitoring
# https://www.elastic.co/guide/en/logstash/current/monitoring-logstash.html
# Flag to allow the legacy internal monitoring (default: false)
#xpack.monitoring.allow_legacy_collection: false
#xpack.monitoring.enabled: false
#xpack.monitoring.elasticsearch.username: logstash_system
#xpack.monitoring.elasticsearch.password: password
#xpack.monitoring.elasticsearch.proxy: ["http://proxy:port"]
#xpack.monitoring.elasticsearch.hosts: ["https://es1:9200", "https://es2:9200"]
# an alternative to hosts + username/password settings is to use cloud_id/cloud_auth
#xpack.monitoring.elasticsearch.cloud_id: monitoring_cluster_id:xxxxxxxxxx
#xpack.monitoring.elasticsearch.cloud_auth: logstash_system:password
# another authentication alternative is to use an Elasticsearch API key
#xpack.monitoring.elasticsearch.api_key: "id:api_key"
#xpack.monitoring.elasticsearch.ssl.certificate_authority: "/path/to/ca.crt"
#xpack.monitoring.elasticsearch.ssl.ca_trusted_fingerprint: xxxxxxxxxx
#xpack.monitoring.elasticsearch.ssl.truststore.path: path/to/file
#xpack.monitoring.elasticsearch.ssl.truststore.password: password
# use either keystore.path/keystore.password or certificate/key configurations
#xpack.monitoring.elasticsearch.ssl.keystore.path: /path/to/file
#xpack.monitoring.elasticsearch.ssl.keystore.password: password
#xpack.monitoring.elasticsearch.ssl.certificate: /path/to/file
#xpack.monitoring.elasticsearch.ssl.key: /path/to/key
#xpack.monitoring.elasticsearch.ssl.verification_mode: full
#xpack.monitoring.elasticsearch.ssl.cipher_suites: []
#xpack.monitoring.elasticsearch.sniffing: false
#xpack.monitoring.collection.interval: 10s
#xpack.monitoring.collection.pipeline.details.enabled: true
#
# X-Pack Management
# https://www.elastic.co/guide/en/logstash/current/logstash-centralized-pipeline-management.html
#xpack.management.enabled: false
#xpack.management.pipeline.id: ["main", "apache_logs"]
#xpack.management.elasticsearch.username: logstash_admin_user
#xpack.management.elasticsearch.password: password
#xpack.management.elasticsearch.proxy: ["http://proxy:port"]
#xpack.management.elasticsearch.hosts: ["https://es1:9200", "https://es2:9200"]
# an alternative to hosts + username/password settings is to use cloud_id/cloud_auth
#xpack.management.elasticsearch.cloud_id: management_cluster_id:xxxxxxxxxx
#xpack.management.elasticsearch.cloud_auth: logstash_admin_user:password
# another authentication alternative is to use an Elasticsearch API key
#xpack.management.elasticsearch.api_key: "id:api_key"
#xpack.management.elasticsearch.ssl.ca_trusted_fingerprint: xxxxxxxxxx
#xpack.management.elasticsearch.ssl.certificate_authority: "/path/to/ca.crt"
#xpack.management.elasticsearch.ssl.truststore.path: /path/to/file
#xpack.management.elasticsearch.ssl.truststore.password: password
# use either keystore.path/keystore.password or certificate/key configurations
#xpack.management.elasticsearch.ssl.keystore.path: /path/to/file
#xpack.management.elasticsearch.ssl.keystore.password: password
#xpack.management.elasticsearch.ssl.certificate: /path/to/file
#xpack.management.elasticsearch.ssl.key: /path/to/certificate_key_file
#xpack.management.elasticsearch.ssl.cipher_suites: []
#xpack.management.elasticsearch.ssl.verification_mode: full
#xpack.management.elasticsearch.sniffing: false
#xpack.management.logstash.poll_interval: 5s

# X-Pack GeoIP Database Management
# https://www.elastic.co/guide/en/logstash/current/plugins-filters-geoip.html#plugins-filters-geoip-manage_update
#xpack.geoip.downloader.enabled: true
#xpack.geoip.downloader.endpoint: "https://geoip.elastic.co/v1/database"
`,
        'jvm.options': `## JVM configuration

# Xms represents the initial size of total heap space
# Xmx represents the maximum size of total heap space

-Xms1g
-Xmx1g

################################################################
## Expert settings
################################################################
##
## All settings below this section are considered
## expert settings. Don't tamper with them unless
## you understand what you are doing
##
################################################################


## Locale
# Set the locale language
#-Duser.language=en

# Set the locale country
#-Duser.country=US

# Set the locale variant, if any
#-Duser.variant=

## basic

# set the I/O temp directory
#-Djava.io.tmpdir=\${HOME}

# set to headless, just in case
-Djava.awt.headless=true

# ensure UTF-8 encoding by default (e.g. filenames)
-Dfile.encoding=UTF-8

# use our provided JNA always versus the system one
#-Djna.nosys=true

## heap dumps

# generate a heap dump when an allocation from the Java heap fails
# heap dumps are created in the working directory of the JVM
-XX:+HeapDumpOnOutOfMemoryError

# specify an alternative path for heap dumps
# ensure the directory exists and has sufficient space
#-XX:HeapDumpPath=\${LOGSTASH_HOME}/heapdump.hprof

## GC logging
#-Xlog:gc*,gc+age=trace,safepoint:file=\${LS_GC_LOG_FILE}:utctime,pid,tags:filecount=32,filesize=64m

# Entropy source for randomness
-Djava.security.egd=file:/dev/urandom

# FasterXML/jackson defaults
#
# Sets the maximum string length (in chars or bytes, depending on input context).
# This limit is not exact and an exception will happen at sizes greater than this limit.
# Some text values that are a little bigger than the limit may be treated as valid but no
# text values with sizes less than or equal to this limit will be treated as invalid.
# This value should be higher than \`logstash.jackson.stream-read-constraints.max-number-length\`.
# The jackson library defaults to 20000000 or 20MB, whereas Logstash defaults to 200MB or 200000000 characters.
#-Dlogstash.jackson.stream-read-constraints.max-string-length=200000000
#
# Sets the maximum number length (in chars or bytes, depending on input context).
# The jackson library defaults to 1000, whereas Logstash defaults to 10000.
#-Dlogstash.jackson.stream-read-constraints.max-number-length=10000
#
# Sets the maximum nesting depth. The depth is a count of objects and arrays that have not
# been closed, \`{\` and \`[\` respectively.
#-Dlogstash.jackson.stream-read-constraints.max-nesting-depth=1000
`,
        'log4j2.properties': `status = error
name = LogstashPropertiesConfig

appender.console.type = Console
appender.console.name = plain_console
appender.console.layout.type = PatternLayout
appender.console.layout.pattern = [%d{ISO8601}][%-5p][%-25c]%notEmpty{[%X{pipeline.id}]}%notEmpty{[%X{plugin.id}]} %m%n

appender.json_console.type = Console
appender.json_console.name = json_console
appender.json_console.layout.type = JSONLayout
appender.json_console.layout.compact = true
appender.json_console.layout.eventEol = true

appender.rolling.type = RollingFile
appender.rolling.name = plain_rolling
appender.rolling.fileName = \${sys:ls.logs}/logstash-plain.log
appender.rolling.filePattern = \${sys:ls.logs}/logstash-plain-%d{yyyy-MM-dd}-%i.log.gz
appender.rolling.policies.type = Policies
appender.rolling.policies.time.type = TimeBasedTriggeringPolicy
appender.rolling.policies.time.interval = 1
appender.rolling.policies.time.modulate = true
appender.rolling.layout.type = PatternLayout
appender.rolling.layout.pattern = [%d{ISO8601}][%-5p][%-25c]%notEmpty{[%X{pipeline.id}]}%notEmpty{[%X{plugin.id}]} %m%n
appender.rolling.policies.size.type = SizeBasedTriggeringPolicy
appender.rolling.policies.size.size = 100MB
appender.rolling.strategy.type = DefaultRolloverStrategy
appender.rolling.strategy.max = 30
appender.rolling.strategy.action.type = Delete
appender.rolling.strategy.action.basepath = \${sys:ls.logs}
appender.rolling.strategy.action.condition.type = IfFileName
appender.rolling.strategy.action.condition.glob = logstash-plain-*
appender.rolling.strategy.action.condition.nested_condition.type = IfLastModified
appender.rolling.strategy.action.condition.nested_condition.age = 7D
appender.rolling.avoid_pipelined_filter.type = PipelineRoutingFilter

appender.json_rolling.type = RollingFile
appender.json_rolling.name = json_rolling
appender.json_rolling.fileName = \${sys:ls.logs}/logstash-json.log
appender.json_rolling.filePattern = \${sys:ls.logs}/logstash-json-%d{yyyy-MM-dd}-%i.log.gz
appender.json_rolling.policies.type = Policies
appender.json_rolling.policies.time.type = TimeBasedTriggeringPolicy
appender.json_rolling.policies.time.interval = 1
appender.json_rolling.policies.time.modulate = true
appender.json_rolling.layout.type = JSONLayout
appender.json_rolling.layout.compact = true
appender.json_rolling.layout.eventEol = true
appender.json_rolling.policies.size.type = SizeBasedTriggeringPolicy
appender.json_rolling.policies.size.size = 100MB
appender.json_rolling.strategy.type = DefaultRolloverStrategy
appender.json_rolling.strategy.max = 30
appender.json_rolling.strategy.action.type = Delete
appender.json_rolling.strategy.action.basepath = \${sys:ls.logs}
appender.json_rolling.strategy.action.condition.type = IfFileName
appender.json_rolling.strategy.action.condition.glob = logstash-json-*
appender.json_rolling.strategy.action.condition.nested_condition.type = IfLastModified
appender.json_rolling.strategy.action.condition.nested_condition.age = 7D
appender.json_rolling.avoid_pipelined_filter.type = PipelineRoutingFilter

appender.routing.type = PipelineRouting
appender.routing.name = pipeline_routing_appender
appender.routing.pipeline.type = RollingFile
appender.routing.pipeline.name = appender-\${ctx:pipeline.id}
appender.routing.pipeline.fileName = \${sys:ls.logs}/pipeline_\${ctx:pipeline.id}.log
appender.routing.pipeline.filePattern = \${sys:ls.logs}/pipeline_\${ctx:pipeline.id}.%i.log.gz
appender.routing.pipeline.layout.type = PatternLayout
appender.routing.pipeline.layout.pattern = [%d{ISO8601}][%-5p][%-25c] %m%n
appender.routing.pipeline.policy.type = SizeBasedTriggeringPolicy
appender.routing.pipeline.policy.size = 100MB
appender.routing.pipeline.strategy.type = DefaultRolloverStrategy
appender.routing.pipeline.strategy.max = 30
appender.routing.pipeline.strategy.action.type = Delete
appender.routing.pipeline.strategy.action.basepath = \${sys:ls.logs}
appender.routing.pipeline.strategy.action.condition.type = IfFileName
appender.routing.pipeline.strategy.action.condition.glob = pipeline_\${ctx:pipeline.id}*.log.gz
appender.routing.pipeline.strategy.action.condition.nested_condition.type = IfLastModified
appender.routing.pipeline.strategy.action.condition.nested_condition.age = 7D

rootLogger.level = \${sys:ls.log.level}
rootLogger.appenderRef.console.ref = \${sys:ls.log.format}_console
rootLogger.appenderRef.rolling.ref = \${sys:ls.log.format}_rolling
rootLogger.appenderRef.routing.ref = pipeline_routing_appender

# Slowlog

appender.console_slowlog.type = Console
appender.console_slowlog.name = plain_console_slowlog
appender.console_slowlog.layout.type = PatternLayout
appender.console_slowlog.layout.pattern = [%d{ISO8601}][%-5p][%-25c] %m%n

appender.json_console_slowlog.type = Console
appender.json_console_slowlog.name = json_console_slowlog
appender.json_console_slowlog.layout.type = JSONLayout
appender.json_console_slowlog.layout.compact = true
appender.json_console_slowlog.layout.eventEol = true

appender.rolling_slowlog.type = RollingFile
appender.rolling_slowlog.name = plain_rolling_slowlog
appender.rolling_slowlog.fileName = \${sys:ls.logs}/logstash-slowlog-plain.log
appender.rolling_slowlog.filePattern = \${sys:ls.logs}/logstash-slowlog-plain-%d{yyyy-MM-dd}-%i.log.gz
appender.rolling_slowlog.policies.type = Policies
appender.rolling_slowlog.policies.time.type = TimeBasedTriggeringPolicy
appender.rolling_slowlog.policies.time.interval = 1
appender.rolling_slowlog.policies.time.modulate = true
appender.rolling_slowlog.layout.type = PatternLayout
appender.rolling_slowlog.layout.pattern = [%d{ISO8601}][%-5p][%-25c] %m%n
appender.rolling_slowlog.policies.size.type = SizeBasedTriggeringPolicy
appender.rolling_slowlog.policies.size.size = 100MB
appender.rolling_slowlog.strategy.type = DefaultRolloverStrategy
appender.rolling_slowlog.strategy.max = 30

appender.json_rolling_slowlog.type = RollingFile
appender.json_rolling_slowlog.name = json_rolling_slowlog
appender.json_rolling_slowlog.fileName = \${sys:ls.logs}/logstash-slowlog-json.log
appender.json_rolling_slowlog.filePattern = \${sys:ls.logs}/logstash-slowlog-json-%d{yyyy-MM-dd}-%i.log.gz
appender.json_rolling_slowlog.policies.type = Policies
appender.json_rolling_slowlog.policies.time.type = TimeBasedTriggeringPolicy
appender.json_rolling_slowlog.policies.time.interval = 1
appender.json_rolling_slowlog.policies.time.modulate = true
appender.json_rolling_slowlog.layout.type = JSONLayout
appender.json_rolling_slowlog.layout.compact = true
appender.json_rolling_slowlog.layout.eventEol = true
appender.json_rolling_slowlog.policies.size.type = SizeBasedTriggeringPolicy
appender.json_rolling_slowlog.policies.size.size = 100MB
appender.json_rolling_slowlog.strategy.type = DefaultRolloverStrategy
appender.json_rolling_slowlog.strategy.max = 30

logger.slowlog.name = slowlog
logger.slowlog.level = trace
logger.slowlog.appenderRef.console_slowlog.ref = \${sys:ls.log.format}_console_slowlog
logger.slowlog.appenderRef.rolling_slowlog.ref = \${sys:ls.log.format}_rolling_slowlog
logger.slowlog.additivity = false

logger.licensereader.name = logstash.licensechecker.licensereader
logger.licensereader.level = info

# Silence http-client by default
logger.apache_http_client.name = org.apache.http
logger.apache_http_client.level = fatal

# Deprecation log
appender.deprecation_rolling.type = RollingFile
appender.deprecation_rolling.name = deprecation_plain_rolling
appender.deprecation_rolling.fileName = \${sys:ls.logs}/logstash-deprecation.log
appender.deprecation_rolling.filePattern = \${sys:ls.logs}/logstash-deprecation-%d{yyyy-MM-dd}-%i.log.gz
appender.deprecation_rolling.policies.type = Policies
appender.deprecation_rolling.policies.time.type = TimeBasedTriggeringPolicy
appender.deprecation_rolling.policies.time.interval = 1
appender.deprecation_rolling.policies.time.modulate = true
appender.deprecation_rolling.layout.type = PatternLayout
appender.deprecation_rolling.layout.pattern = [%d{ISO8601}][%-5p][%-25c]%notEmpty{[%X{pipeline.id}]}%notEmpty{[%X{plugin.id}]} %m%n
appender.deprecation_rolling.policies.size.type = SizeBasedTriggeringPolicy
appender.deprecation_rolling.policies.size.size = 100MB
appender.deprecation_rolling.strategy.type = DefaultRolloverStrategy
appender.deprecation_rolling.strategy.max = 30

logger.deprecation.name = org.logstash.deprecation
logger.deprecation.level = WARN
logger.deprecation.appenderRef.deprecation_rolling.ref = deprecation_plain_rolling
logger.deprecation.additivity = true

logger.deprecation_root.name = deprecation
logger.deprecation_root.level = WARN
logger.deprecation_root.appenderRef.deprecation_rolling.ref = deprecation_plain_rolling
logger.deprecation_root.additivity = true
`
    };
    
    // Make fileContents globally accessible for save function
    window.policyFileContents = fileContents;
    
    // Initialize CodeMirror
    function initCodeMirror() {
        const textarea = document.getElementById('codeEditor');
        if (!textarea) return;
        
        editor = CodeMirror.fromTextArea(textarea, {
            lineNumbers: true,
            mode: 'text/x-yaml',
            indentUnit: 2,
            tabSize: 2,
            indentWithTabs: false,
            lineWrapping: true,
            matchBrackets: true,
            autoCloseBrackets: true,
            extraKeys: {
                "Tab": function(cm) {
                    cm.replaceSelection("  ", "end");
                }
            }
        });
        
        // Make editor globally accessible
        window.policyEditor = editor;
        
        // Set initial content
        editor.setValue(fileContents[currentFile]);
        
        // Auto-refresh to ensure proper rendering
        setTimeout(() => {
            editor.refresh();
        }, 100);
    }
    
    // File tab switching
    document.querySelectorAll('.file-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const file = this.dataset.file;
            
            // Update active tab
            document.querySelectorAll('.file-tab').forEach(t => {
                t.classList.remove('active');
                const span = t.querySelector('span');
                if (span) {
                    span.classList.remove('text-white');
                    span.classList.add('text-gray-400');
                }
            });
            this.classList.add('active');
            const span = this.querySelector('span');
            if (span) {
                span.classList.remove('text-gray-400');
                span.classList.add('text-white');
            }
            
            // Store current file before switching
            const previousFile = currentFile;
            currentFile = file;
            
            // Update global currentFile reference
            window.policyCurrentFile = file;
            
            // Show/hide mode toggle based on file type (only for logstash.yml)
            const modeToggleContainer = document.getElementById('modeToggleContainer');
            if (file === 'logstash.yml') {
                modeToggleContainer.classList.remove('hidden');
                // Automatically switch to Form mode for logstash.yml
                switchToFormMode();
            } else {
                modeToggleContainer.classList.add('hidden');
                // Automatically switch to Code mode for jvm.options and log4j2.properties
                switchToCodeMode();
            }
            
            if (editor) {
                // Save current content of previous file before switching
                if (previousFile && editor.getValue()) {
                    fileContents[previousFile] = editor.getValue();
                }
                
                // Update mode based on file type
                let mode = 'text/plain';
                if (file.endsWith('.yml')) {
                    mode = 'text/x-yaml';
                } else if (file.endsWith('.options') || file.endsWith('.properties')) {
                    // Use simple comment mode for jvm.options and log4j2.properties
                    mode = 'text/x-simplecomment';
                }
                editor.setOption('mode', mode);
                
                // Load new file content
                editor.setValue(fileContents[file] || '');
                editor.refresh();
            }
        });
    });
    
    // Mode toggle (Form/Code)
    const formModeBtn = document.getElementById('formModeBtn');
    const codeModeBtn = document.getElementById('codeModeBtn');
    const formModeEditor = document.getElementById('formModeEditor');
    const codeModeEditor = document.getElementById('codeModeEditor');
    
    function switchToFormMode() {
        currentMode = 'form';
        formModeBtn.classList.add('active');
        codeModeBtn.classList.remove('active');
        formModeEditor.classList.remove('hidden');
        codeModeEditor.classList.add('hidden');
    }
    
    function switchToCodeMode() {
        currentMode = 'code';
        codeModeBtn.classList.add('active');
        formModeBtn.classList.remove('active');
        codeModeEditor.classList.remove('hidden');
        formModeEditor.classList.add('hidden');
        
        // Initialize CodeMirror if not already done
        if (!editor) {
            initCodeMirror();
        } else {
            editor.refresh();
        }
    }
    
    formModeBtn.addEventListener('click', switchToFormMode);
    codeModeBtn.addEventListener('click', switchToCodeMode);
    
    // Global Config toggle
    const globalConfigToggle = document.getElementById('globalConfigToggle');
    const globalConfigContent = document.getElementById('globalConfigContent');
    const globalConfigChevron = document.getElementById('globalConfigChevron');
    
    globalConfigToggle.addEventListener('click', function() {
        globalConfigContent.classList.toggle('hidden');
        globalConfigChevron.classList.toggle('rotate-180');
    });
    
    // Save button
    document.getElementById('saveBtn').addEventListener('click', savePolicyChanges);
    
    // Deploy button
    document.getElementById('deployBtn').addEventListener('click', function() {
        console.log('Deploying policy...');
        
        // TODO: Implement actual deploy functionality
        alert('Deploy functionality will be implemented soon');
    });
    
    // Policy dropdown change handler
    const policySelect = document.getElementById('policySelect');
    const defaultPolicyIndicator = document.getElementById('defaultPolicyIndicator');
    const saveBtn = document.getElementById('saveBtn');
    const deployBtn = document.getElementById('deployBtn');
    
    policySelect.addEventListener('change', async function() {
        const selectedValue = this.value;
        
        if (selectedValue === 'add_new') {
            // Show popup to add new policy
            const policyName = await ConfirmationModal.prompt(
                'Enter a name for the new policy:',
                '',
                'Add New Policy',
                'e.g., Production Policy'
            );
            
            if (policyName && policyName.trim()) {
                const trimmedName = policyName.trim();
                
                // Check if policy already exists
                if (customPolicies.includes(trimmedName) || trimmedName.toLowerCase() === 'default policy') {
                    await ConfirmationModal.show(
                        'A policy with this name already exists. Please choose a different name.',
                        'Duplicate Policy Name',
                        'OK',
                        null,
                        true
                    );
                    // Reset to current policy
                    this.value = currentPolicy;
                    return;
                }
                
                // Make HTMX call to add policy
                try {
                    const response = await fetch('/ConnectionManager/AddPolicy/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({
                            name: trimmedName,
                            settings_path: document.getElementById('settingsPath').value,
                            logs_path: document.getElementById('logsPath').value,
                            logstash_yml: fileContents['logstash.yml'],
                            jvm_options: fileContents['jvm.options'],
                            log4j2_properties: fileContents['log4j2.properties']
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        // Add new policy to the list
                        customPolicies.push(trimmedName);
                        
                        // Add option to dropdown (before the + Add Policy option)
                        const addNewOption = this.querySelector('option[value="add_new"]');
                        const newOption = document.createElement('option');
                        newOption.value = trimmedName.toLowerCase().replace(/\s+/g, '_');
                        newOption.textContent = trimmedName;
                        newOption.dataset.policyName = trimmedName;
                        this.insertBefore(newOption, addNewOption);
                        
                        // Select the new policy
                        this.value = newOption.value;
                        currentPolicy = newOption.value;
                        
                        // Update UI for custom policy
                        updatePolicyUI(false);
                        
                        showToast(data.message, 'success');
                    } else {
                        showToast(data.error || 'Failed to create policy', 'error');
                        this.value = currentPolicy;
                    }
                } catch (error) {
                    console.error('Error creating policy:', error);
                    showToast('Failed to create policy: ' + error.message, 'error');
                    this.value = currentPolicy;
                }
            } else {
                // User cancelled or entered empty name, reset to current policy
                this.value = currentPolicy;
            }
        } else {
            // Regular policy selection
            currentPolicy = selectedValue;
            
            // Update UI based on whether it's the default policy
            const isDefaultPolicy = selectedValue === 'default';
            updatePolicyUI(isDefaultPolicy);
            
            // Load policy data into form if it's a custom policy
            if (!isDefaultPolicy) {
                // Fetch fresh policy data from database
                loadPolicyData(selectedValue);
            }
        }
    });
    
    // Function to update UI based on policy type
    function updatePolicyUI(isDefaultPolicy) {
        const deletePolicyBtn = document.getElementById('deletePolicyBtn');
        const settingsPathInput = document.getElementById('settingsPath');
        const logsPathInput = document.getElementById('logsPath');
        
        if (isDefaultPolicy) {
            // Show read-only indicator
            defaultPolicyIndicator.classList.remove('hidden');
            
            // Hide delete button for default policy
            deletePolicyBtn.classList.add('hidden');
            
            // Disable save button for default policy
            saveBtn.disabled = true;
            saveBtn.classList.add('opacity-50', 'cursor-not-allowed');
            saveBtn.title = 'Default Policy is read-only';
            
            // Disable form inputs
            if (settingsPathInput) {
                settingsPathInput.disabled = true;
                settingsPathInput.classList.add('opacity-50', 'cursor-not-allowed');
            }
            if (logsPathInput) {
                logsPathInput.disabled = true;
                logsPathInput.classList.add('opacity-50', 'cursor-not-allowed');
            }
            
            // Disable CodeMirror editor (but keep it visible and navigable)
            if (editor) {
                editor.setOption('readOnly', true);
                editor.getWrapperElement().style.opacity = '0.6';
                editor.getWrapperElement().style.cursor = 'not-allowed';
            }
            
            // Keep mode toggle buttons enabled so users can switch views
            // (editor will still be read-only)
            
            // Keep deploy button enabled
            deployBtn.disabled = false;
            deployBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            // Hide read-only indicator
            defaultPolicyIndicator.classList.add('hidden');
            
            // Show delete button for custom policies
            deletePolicyBtn.classList.remove('hidden');
            
            // Enable save button for custom policies
            saveBtn.disabled = false;
            saveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            saveBtn.title = '';
            
            // Enable form inputs
            if (settingsPathInput) {
                settingsPathInput.disabled = false;
                settingsPathInput.classList.remove('opacity-50', 'cursor-not-allowed');
            }
            if (logsPathInput) {
                logsPathInput.disabled = false;
                logsPathInput.classList.remove('opacity-50', 'cursor-not-allowed');
            }
            
            // Enable CodeMirror editor
            if (editor) {
                editor.setOption('readOnly', false);
                editor.getWrapperElement().style.opacity = '1';
                editor.getWrapperElement().style.cursor = 'text';
            }
            
            // Mode toggle buttons are always enabled
            
            // Keep deploy button enabled
            deployBtn.disabled = false;
            deployBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    
    // Load policies on page load
    loadPolicies();
    
    // Initialize UI for default policy (read-only)
    updatePolicyUI(true);
    
    // Initialize in Form mode by default
    // (Form mode is already active by default in HTML)
});

// Load specific policy data from the server
async function loadPolicyData(policyValue) {
    try {
        const response = await fetch('/ConnectionManager/GetPolicies/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success && data.policies) {
            // Find the policy by matching the value
            const policySelect = document.getElementById('policySelect');
            const selectedOption = policySelect.options[policySelect.selectedIndex];
            const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
            
            const policy = data.policies.find(p => p.name === policyName);
            
            if (policy) {
                // Update form fields
                document.getElementById('settingsPath').value = policy.settings_path;
                document.getElementById('logsPath').value = policy.logs_path;
                
                // Update file contents with fresh data from database
                window.policyFileContents['logstash.yml'] = policy.logstash_yml;
                window.policyFileContents['jvm.options'] = policy.jvm_options;
                window.policyFileContents['log4j2.properties'] = policy.log4j2_properties;
                
                // Update editor if it's initialized and showing current file
                if (window.policyEditor && window.policyCurrentFile) {
                    window.policyEditor.setValue(window.policyFileContents[window.policyCurrentFile] || '');
                    window.policyEditor.refresh();
                }
            }
        }
    } catch (error) {
        console.error('Error loading policy data:', error);
        showToast('Failed to load policy data: ' + error.message, 'error');
    }
}

// Load all policies from the server
async function loadPolicies() {
    try {
        const response = await fetch('/ConnectionManager/GetPolicies/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success && data.policies) {
            const policySelect = document.getElementById('policySelect');
            const addNewOption = policySelect.querySelector('option[value="add_new"]');
            
            // Clear existing custom policies (keep Default and + Add Policy)
            const options = Array.from(policySelect.options);
            options.forEach(option => {
                if (option.value !== 'default' && option.value !== 'add_new') {
                    option.remove();
                }
            });
            
            // Add policies from server
            data.policies.forEach(policy => {
                // Skip if it's the default policy (already in dropdown)
                if (policy.name.toLowerCase() === 'default policy') {
                    return;
                }
                
                const option = document.createElement('option');
                option.value = policy.name.toLowerCase().replace(/\s+/g, '_');
                option.textContent = policy.name;
                option.dataset.policyName = policy.name;
                option.dataset.policyId = policy.id;
                
                // Store policy data for later use
                option.dataset.settingsPath = policy.settings_path;
                option.dataset.logsPath = policy.logs_path;
                option.dataset.logstashYml = policy.logstash_yml;
                option.dataset.jvmOptions = policy.jvm_options;
                option.dataset.log4j2Properties = policy.log4j2_properties;
                
                // Insert before "+ Add Policy" option
                policySelect.insertBefore(option, addNewOption);
                
                // Add to customPolicies array
                if (!window.customPolicies) {
                    window.customPolicies = [];
                }
                window.customPolicies.push(policy.name);
            });
        }
    } catch (error) {
        console.error('Error loading policies:', error);
        showToast('Failed to load policies: ' + error.message, 'error');
    }
}

// Get CSRF token from cookie
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Save policy changes
async function savePolicyChanges() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
    
    if (policySelect.value === 'default') {
        showToast('Cannot save changes to Default Policy', 'error');
        return;
    }
    
    // Get the current editor instance and save current content to fileContents
    const settingsPath = document.getElementById('settingsPath').value;
    const logsPath = document.getElementById('logsPath').value;
    
    // If editor is active, save current editor content to fileContents
    if (window.policyEditor && window.policyFileContents) {
        // Get the current file being edited
        const currentFile = window.policyCurrentFile || 'logstash.yml';
        // Save current editor content to fileContents
        window.policyFileContents[currentFile] = window.policyEditor.getValue();
    }
    
    try {
        const response = await fetch('/ConnectionManager/UpdatePolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_name: policyName,
                settings_path: settingsPath,
                logs_path: logsPath,
                logstash_yml: window.policyFileContents ? window.policyFileContents['logstash.yml'] : '',
                jvm_options: window.policyFileContents ? window.policyFileContents['jvm.options'] : '',
                log4j2_properties: window.policyFileContents ? window.policyFileContents['log4j2.properties'] : ''
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error || 'Failed to update policy', 'error');
        }
    } catch (error) {
        console.error('Error updating policy:', error);
        showToast('Failed to update policy: ' + error.message, 'error');
    }
}

// Delete current policy
async function deleteCurrentPolicy() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
    
    if (policySelect.value === 'default') {
        showToast('Cannot delete Default Policy', 'error');
        return;
    }
    
    const confirmed = await ConfirmationModal.show(
        `Are you sure you want to delete the policy "${policyName}"?\n\nThis action cannot be undone.`,
        'Delete Policy',
        'Delete',
        null,
        false
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch('/ConnectionManager/DeletePolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_name: policyName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Remove from dropdown
            selectedOption.remove();
            
            // Remove from custom policies array
            const index = window.customPolicies.indexOf(policyName);
            if (index > -1) {
                window.customPolicies.splice(index, 1);
            }
            
            // Switch to default policy
            policySelect.value = 'default';
            window.currentPolicy = 'default';
            updatePolicyUI(true);
            
            showToast(data.message, 'success');
        } else {
            showToast(data.error || 'Failed to delete policy', 'error');
        }
    } catch (error) {
        console.error('Error deleting policy:', error);
        showToast('Failed to delete policy: ' + error.message, 'error');
    }
}
