## [0.5.0] - NMS release - 07/21/2026

### Added

- Added a complete SNMP network management application for discovering, onboarding, configuring, monitoring, and deploying network devices through Logstash.
- Added a consolidated onboarding experience for device discovery, manual device setup, and AI-assisted device generation.
- Added a modal-based Device Wizard workflow so users remain on the Device Wizard page throughout onboarding.
- Added AI-assisted SNMP device onboarding that can:
  - Walk a device.
  - Identify device capabilities.
  - Generate device templates and profiles.
  - Allow iterative review and refinement.
  - Approve and deploy generated configurations.
- Added inline MIB-grounded AI authoring without requiring a separate runtime knowledge base.
- Added full-column SNMP discovery walks to improve grounding coverage during AI generation.
- Added support for re-onboarding devices without failing when an existing template or profile has the same name.
- Added official SNMP device templates and profiles for a wider range of network devices.
- Added initial Ubiquiti access point profiles and templates.
- Added a generic `Default` device template that acts as a catchall for devices without an explicitly assigned template.
- Added device type classification to device templates.
- Added official-template tracking to distinguish built-in templates from user-created templates.
- Added images to device, network, template, and profile interfaces to make objects easier to identify.
- Added card-based metric visuals for:
  - CPU cores.
  - Wireless radios.
  - CDP and LLDP neighbors.
  - Filesystems.
  - Printer ink and consumables.
- Added configurable profile normalizers, replacing the previous hard-coded field-normalization implementation.
- Added normalizers for:
  - Field renaming.
  - Multiplication.
  - Division.
  - Ratios.
  - Ratios calculated from table rows.
  - Column averages.
  - Translate mappings.
- Added support for carrying user-authored and AI-authored normalizers through onboarding, approval, synchronization, and pipeline generation.
- Added Time Series Data Stream support for generated SNMP metrics.
- Added time-series dimensions and index-template installation during deployment.
- Added configurable namespaces for SNMP data streams.
- Added support for separating SNMP data streams by:
  - A shared namespace.
  - Network namespace.
  - Device-template namespace.
- Added a network-level option to create namespaces per device template.
- Added editable Elasticsearch connections.
- Added automatic invalidation of stale credentials when an Elasticsearch connection is edited.
- Added Logstash Agent support for SNMP pipeline deployment and management.
- Added Logstash Agent information to the agent inspection Process tab.
- Added support for identifying agents managed through Centralized Pipeline Management when a sibling connection is used for management.
- Added keystore discovery for Centralized Pipeline Management connections.
- Added support for plaintext SNMP credentials in generated pipelines when keystores are not being used.
- Added SNMP credential and connectivity testing throughout the SNMP application.
- Added clearer SNMP test results for:
  - Invalid credentials.
  - Connection timeouts.
  - Devices that do not respond.
- Added SNMP walk testing for troubleshooting and future AI template generation.
- Added discovery-pipeline generation for empty networks that have discovery enabled.
- Added safeguards preventing discovery configuration for networks larger than `/20`.
- Added device-level location and arbitrary metadata fields.
- Added configurable metadata enrichment for generated SNMP events.
- Added device counts to the credentials page.
- Added credential-table pagination with page sizes of 25, 50, 100, and 200.
- Added asynchronous search and loading for credential selectors.
- Added searchable device-template selectors.
- Added custom image-based device-template selection controls.
- Added expandable editors for large text fields such as Grok patterns and Dissect mappings.
- Added support for preserving comments inside plugin configurations.
- Added support for regular expressions in pipeline conditions.
- Added a Logstash and LogstashUI compatibility matrix.
- Added comprehensive SNMP architecture, onboarding, deployment, and operations documentation.
- Added documentation for:
  - Creating credentials.
  - Creating networks.
  - Discovering devices.
  - Assigning templates and profiles.
  - Committing and deploying changes.
  - SNMP pipeline generation.
  - Discovery behavior and limitations.
  - Undeployed-change workflows.
  - SNMP trap support.
  - Simulation and test data.
  - Logstash Agent compatibility.
  - Deployment-mode differences.
  - Embedded Docker Compose deployments.
  - Building and running LogstashUI from source.
  - AI Device Onboarding.
  - Inline AI grounding.
  - Contributing device walks and official profiles.
- Added automated tests for SNMP CRUD operations, views, synchronization commands, AI onboarding, normalizers, and discovery walks.
- Added regression tests for scope-qualified normalizer filter IDs.
- Added the required license attribution for Marked.js.

### Changed

- Changed SNMP pipeline generation to generate and reconcile pipelines by device template rather than by every profile combination.
- Overhauled SNMP pipeline generation and reconciliation for significantly larger deployments.
- Changed generated enrichment to operate at the device-template level.
- Changed the default SNMP polling interval from 30 seconds to 60 seconds.
- Changed `event.kind` usage to `event.category`.
- Changed `host.description` to `observer.sys_descr` to align with the Kibana network map schema.
- Added `host.type` enrichment from the assigned device template.
- Added `observer.vendor` enrichment from device profiles.
- Updated the SNMP schema to better align with gNMI field conventions.
- Normalized field names across official SNMP profiles and templates.
- Normalized the generic host-system metrics profile.
- Updated generic host-system metrics to detect and normalize available memory metrics.
- Updated table unpacking to use dot-separated table names.
- Changed generated table names so they use the actual table name rather than always being prefixed with `table`.
- Removed the former special-case filter generator after replacing its behavior with configurable normalization.
- Restricted the remaining Ruby filter generation helper to table-splitting behavior.
- Updated ratio normalization to support ordinary division and table rows.
- Scope-qualified multiply and ratio normalizer filter IDs to prevent collisions.
- Updated template and profile synchronization to clean up obsolete official files.
- Moved official SNMP synchronization helpers into a dedicated location.
- Updated discovery to query only SNMP connections currently used by relevant networks.
- Changed discovery behavior to better support devices configured with hostnames rather than IP addresses.
- Updated device identity handling to distinguish:
  - User-assigned names.
  - Discovered system names.
  - DNS names.
  - IP addresses.
- Added IP detection so valid addresses are populated into `host.ip`.
- Updated the network map architecture and made network-map nodes interactive.
- Updated the network-map index used by SNMP views.
- Replaced the device-quality table with a device-template coverage matrix.
- Updated interface health colors:
  - Green for healthy.
  - Yellow for warning.
  - Red for critical.
  - Gray for unknown or administratively down.
- Updated SNMP metric visuals after schema and normalization changes.
- Updated template and profile image sizing.
- Removed the arbitrary Logstash node name from network configuration.
- Removed the Created column from device and credential tables.
- Changed credential loading from server-side rendering to asynchronous JavaScript loading.
- Changed related-object dropdowns to refresh automatically after objects are created in nested modals.
- Removed manual refresh buttons from supported CRUD selectors.
- Changed the plugin configuration search bar so it is visually distinct from configuration fields.
- Standardized SNMP device and network modal inputs.
- Changed the device-template selector to display formatted names and images instead of raw object values.
- Changed the SNMP Devices navigation indicator so it stops pulsing after the user visits the page.
- Updated context processors so the SNMP Devices page only pulses when attention is actually required.
- Updated the Device Wizard template-generation path to remain within the onboarding workflow.
- Changed the AI generation button to clearly indicate unavailable or upcoming functionality where appropriate.
- Replaced the former instruction modal with direct links to documentation.
- Updated deployment progress messaging so smaller deployments no longer warn that they may take several minutes.
- Updated the SNMP walk warning to be more direct.
- Added `system.location` and `system.contact` to the generic system profile.
- Updated Ubiquiti access point uptime polling.
- Removed deprecated profile interfaces and duplicated onboarding functionality.
- Consolidated duplicate `escapeHtml` implementations into the shared base JavaScript module.
- Removed orphaned functions, deprecated helpers, and duplicated code.
- Replaced remaining `print` statements with structured logger calls.
- Added missing administrator authorization checks to SNMP CRUD operations.
- Updated feature gating for SNMP, Centralized Pipeline Management, and traditional Logstash deployment modes.
- Updated the Logstash Agent installation validation to support Logstash installations built or run from source.
- Added jitter to Logstash Agent polling timers.
- Updated Logstash Agent documentation and deployment guidance.
- Updated source-build documentation and minimum system requirements.
- Updated compatibility assets for Logstash 9.4.
- Updated the LogstashUI introductory workshop for the NMS release.
- Improved general UI text, spacing, formatting, and consistency throughout the SNMP application.

### Fixed

- Fixed undeployed-change indicators not clearing after a successful deployment.
- Fixed undeployed-change indicators not appearing or updating correctly after CRUD operations.
- Fixed some network, profile, and template operations failing to trigger the deploy-changes animation.
- Fixed orphaned discovery-pipeline detection overlapping with pipeline deletion.
- Fixed empty discovery-enabled networks not generating discovery pipelines.
- Fixed stale and orphaned generated pipelines not being reconciled correctly.
- Fixed collisions between generated normalizer IDs.
- Fixed multiply and ratio normalizer filter IDs colliding across scopes.
- Fixed AI-authored and user-authored normalizers being dropped during onboarding and pipeline generation.
- Fixed generated profiles losing normalizer configuration.
- Fixed device templates being left empty after a template was deleted.
- Fixed devices without an assigned template by automatically assigning the `Default` template.
- Fixed device-template profile selectors displaying database IDs instead of readable profile names.
- Fixed device-template names being formatted incorrectly in device configuration workflows.
- Fixed official profile and template synchronization issues on Windows.
- Fixed data consistency problems in SNMP profile and template synchronization commands.
- Fixed the renamed `sysDescr` field breaking generated output.
- Fixed missing SNMP metadata in generated `add_field` configuration.
- Fixed Cisco IOS profile metrics that were using an incorrect index.
- Fixed Ubiquiti access point normalizers conflicting with unrelated fields.
- Fixed access point uptime polling using the wrong metric.
- Fixed an orphaned component table in the entity-sensor profile.
- Fixed table normalizers failing to calculate averages correctly.
- Fixed commented fields containing hash values being parsed as active configuration.
- Fixed inline comments containing `{` or `}` causing pipeline-parser errors.
- Fixed plugin comments being discarded instead of preserved.
- Fixed regular expressions in conditions being rejected by the pipeline AST.
- Fixed large text inputs being difficult to inspect and edit.
- Fixed modal input and select controls closing immediately after being clicked.
- Fixed a credentials-table JavaScript error caused by a missing closing brace.
- Fixed credential selectors and CRUD dropdowns failing to update after new objects were created.
- Fixed SNMP tests presenting ambiguous failures for credential errors and timeouts.
- Fixed discovery querying every configured connection instead of only relevant SNMP connections.
- Fixed hostname-based devices being handled incorrectly during discovery.
- Fixed the SNMP Devices page continuing to pulse after it had been visited.
- Fixed the network map using the wrong backing index.
- Fixed network-map rendering after schema changes.
- Fixed fresh installations failing when the last-seen timestamp was null.
- Fixed device and network views exposing inconsistent or incomplete names.
- Fixed missing migrations associated with new SNMP templates, profiles, namespaces, and Logstash Agent functionality.
- Fixed generated device onboarding failing when an approved object reused an existing name.
- Fixed AI discovery walks skipping columns and producing incomplete grounding data.
- Fixed incorrect interactions and state synchronization between LogstashUI and Logstash Agent.
- Fixed Logstash Agent process information being presented as though it were the Logstash process.
- Fixed missing RBAC protection across SNMP administrative operations.
- Fixed installation-asset actions, loading indicators, and cleanup behavior in AI template and profile generation.
- Fixed various SNMP CRUD, rendering, deployment, and code-quality issues discovered during final release testing.



## [0.4.3] - AI Foundation, Simulation Improvements, and SNMP Fixes - 06/07/2026

### Added

- Added an Elastic Serverless indicator after successfully testing a connection.
- Added foundational support for AI agents.
- Added Integration Factory as an experimental feature.
- Added system architecture documentation and linked it from the README.

### Changed

- Updated simulation mode to use port `9650` instead of `9600` to avoid conflicts with Logstash monitoring APIs.
- Normalized language around simulation nodes in the pipeline editor.
- Updated condition editing controls so they appear as clear edit buttons instead of inline pencil icons in both graph and inline modes.
- Updated Integration Factory so it only uses connections configured with Cloud IDs.

### Fixed

- Fixed an issue where simulated document batches could incorrectly show the “no plugins executed” banner for all documents when only a single document returned no results.
- Fixed an issue where simulation continued searching for results after the final document response had already been received.
- Fixed the walk profile caution message so it appears again when rows are added to a walk profile.
- Fixed generated SNMP pipelines so they include the port when connections do not use a Cloud ID, preventing incorrect default port behavior.
- Added additional simulation-mode agent logging to help diagnose agent issues.

## [0.4.2] - SNMP Expansion, Settings, and AI Foundation - 05/14/2026

### Added

- Added global settings support with an initial Experimental Mode setting.
- Added the initial AI / chat app foundation.
- Added the ability to test an SNMP connection and device template directly from the SNMP UI.
- Added an SNMP overview page with initial KPI cards, visualizations, queries, and network summary data.
- Added a CDP-based network map for SNMP adjacency visualization.
- Added CDP adjacency data to the SNMP data quality table.
- Added an agent view to the policy page in preparation for feature flags.
- Added Logstash node visibility to agent policies.
- Added a deploy button glow when there are undeployed changes.
- Added support for cloning SNMP-related objects.
- Added interfaces as a core field in the device data quality check.
- Added `sysObjectID` to the generic system profile.
- Added an Epson device template.
- Added automatic SNMP profile / template detection.
- Added device template assignment suggestions based on detected device metadata such as `sysDescr`.
- Added template suggestion context, including name, description, vendor, family/type, model, matching field, official status, and associated profiles.
- Added handling for cases where no strong device template match is available.
- Added hover descriptions and explanatory text across SNMP CRUD pages.
- Added dedicated SNMP setup documentation and linked to it from the SNMP UI.

### Changed

- Incremented the version number to `0.4.2`.
- Renamed SNMP “Commit Changes” language to “Deploy Changes” for clearer deployment semantics.
- Reduced the discovery modal to show devices seen in the last 10 minutes instead of the last 2 hours.
- Normalized SNMP “Add” button sizing across pages.
- Overhauled the SNMP profile page and removed/changed older pinning behavior.
- Updated SNMP CRUD pages so creating, updating, and deleting values no longer requires a full page reload.
- Replaced the offline symbol with a loading spinner while device information is being fetched from Elasticsearch.
- Added last successful poll / last seen visibility for SNMP devices.
- Added a startup / management sync process for official SNMP profiles instead of re-syncing profiles on page load.
- Updated official SNMP profile sync behavior to remove unused official profiles that are no longer present in the official profile set.
- Replaced the old profile-to-device relationship model with the newer profile-to-template relationship model.
- Removed deprecated profile-to-device junction table usage.
- Moved inline HTML CSS into dedicated CSS files where Tailwind could not be used.
- Moved “Click here for setup instructions” content into a dedicated documentation page and updated the UI to reference that page.
- Added top-of-page explanatory text to SNMP pages describing what each component does and linking to relevant documentation.

### Fixed

- Fixed SNMP connection modal styling on SNMP pages.
- Fixed broken documentation app link rewriting.
- Updated documentation compatibility details for Elastic / Logstash `8.x` and `9.x`.
- Improved SNMP template matching behavior, including tie-breaker handling for competing matches.

### Documentation

- Updated in-app SNMP setup instructions.
- Added SNMP setup documentation.
- Added compatibility documentation for `8.x` and `9.x`.
- Added contextual descriptions for SNMP CRUD pages and linked related docs from the UI.

## [0.4.1] - Post 0.4.0 Polish - 04/20/2026

### Added

- Added an undeployed-changes indicator across SNMP-related pages to make pending SNMP changes more visible.
- Added goto input and goto output navigation buttons in the graph editor.
- Added a global scroll-to-top control that appears after scrolling far enough down a page.
- Added support for closing modals globally by pressing `Esc`.
- Added a `CONTRIBUTING.md` guide for project contributors.

### Changed

- Replaced browser-native confirmation and dialog boxes with the application's native popup experience.
- Centralized toast handling in `base.js` and removed older SNMP-specific `showToast` usage.
- Improved documentation structure and organization to make it easier to navigate.
- Updated automation for generating NOTICE content and license headers.
- Removed concurrent rotating file handlers to avoid ongoing complexity from an inconvenient transitive dependency.

### Fixed

- Fixed Docker packaging so the `/docs/` directory is copied into the image and the in-app documentation feature works as expected.

## [0.4.0] - Logstash Agent - 04/18/2026

### Added

- Added centralized Logstash Agent management, including policy creation, enrollment, and agent-aware connection workflows.
- Added support for managing pipelines through Logstash Agent, including pipeline settings and policy-level pipeline organization.
- Added keystore management improvements, including password management, clearer visibility into sensitive fields, and support for deploying keystore-related changes independently.
- Added agent operational controls such as restart support, upgrade support, health reporting, and richer status details.
- Added live status and log streaming improvements to make troubleshooting and monitoring easier.
- Added validation to help catch missing Logstash installations, invalid paths, and other configuration issues earlier.
- Added clearer deployment feedback, including indicators for undeployed changes and warnings for situations that require special handling.
- Added an in-app documentation experience.
- Added expanded automated testing and coverage reporting.

### Changed

- Improved the overall Logstash Agent experience across enrollment, policy management, deployment workflows, and health visibility.
- Improved the safety of deployments so failed changes are handled more cleanly and unnecessary restarts are reduced.
- Improved the UI across connection management, policy views, agent health/status displays, and navigation.
- Improved security for communication between LogstashUI and Logstash Agent.
- Reworked packaging and project structure to support the ongoing evolution of Logstash Agent.
- Moved documentation into the application for a more integrated user experience.
- Updated SNMP-related UI flows and made minor usability improvements.

### Fixed

- Fixed navigation state so collapsed navigation sections now persist more reliably.
- Fixed several deployment and keystore edge cases that could cause failed or blocked changes.
- Fixed pipeline change detection issues so edits are recognized more reliably.
- Fixed agent status and health display issues.
- Fixed several policy, pipeline, and configuration UI bugs.
- Fixed monitoring behavior to better align with centralized connection workflows.
- Fixed documentation image/link issues.
- Fixed a number of packaging, path, logging, and platform-specific issues introduced during refactoring.


## [0.3.5] - 03/23/2026
### Changed
- Disabled light mode entirely


## [0.3.4] - 03/17/2026
### Changed
- Quick fix to make simulation of dropped messages work universally

## [0.3.3] - 03/17/2026

### Added
- Converted delete alerts/confirmation boxes to use stylized popup components  
- Saving a pipeline now shows a toast notification instead of shifting UI elements  

### Changed
- Pipeline manager table now displays hostname when a node is added via URL instead of Cloud ID  
- Defaulted `logstashagent.yml` to Linux configuration  

### Fixed
- Improved handling of messages sent to pipelines that never loaded  
- Fixed pipeline eviction issue caused by runtime config not being properly detected  

## [0.3.2] - 03/16/2026
### Changed
Fixed elastic host connection string

## [0.3.1] - 03/16/2026

### Added
Added a search bar to the top of the plugin config modal

### Changed
Allow unverified elastic connections
Swapped a javascript alert for our popup box (styled it)

### Fixed
Fixed minor visual line bugs in the graph

## [0.3.0] - 03/16/2026

### Added
- Host mode for Windows and Linux with environment variable preservation
- Log files for LogstashAgent
- Scripts for Linux host mode
- Runtime configuration (replaces build-time config)
- Startup scripts that force shutdown first and manage a `.venv` file
- Graph view in the Pipeline Editor with recursive nested condition support
- Custom popup/modal to replace native browser alerts, matching app theme
- Ability to validate pipelines on click
- Stats strip in the Pipeline Editor
- User preference persistence for last-used editor mode (text vs. graph)
- Toggle in text mode to suppress mode-switch confirmation popup
- Regression tests for Common, Management, Monitoring, PipelineManager, Site, SNMP, and Utilities
- `popup.html` for themed in-app alerts
- GitAttributes file to prevent line ending changes on commit

### Changed
- Default simulation mode is now `embedded`
- ElasticAgent simulation node now listens on localhost only instead of all interfaces
- Logstash supervisor tuned to be more aggressive on restarts and better handle large pipeline simulations
- Startup scripts now activate and manage a `.venv` instead of installing dependencies directly
- Reworked Pipeline Editor top bar UI — more responsive and reactive
- Updated Dockerfile and Docker Compose to support server, development, and Docker Compose modes
- Renamed and reorganized docs
- Text editor behavior now consistent when switching between text and graph modes
- Default YML config example reset to clean state

### Fixed
- Linux host mode permissions and file permission quirks
- Database not persisting due to path mismatch
- Stop script now more reliably terminates the agent
- Testing config now works with the supplied binary instead of hardcoded Linux path
- Windows Server limitations documented for host mode
- Drop return path for pipelines

## [0.2.1] - 03/05/2026

### Added
- Documentation links inside the plugin configuration modal
- Initial implementation of a visual expression editor (foundation for future condition builder)
- Ability to load Logstash plugin documentation directly within LogstashUI
- Label showing the slowest plugin during pipeline simulation
- Icons for filter plugins in the pipeline editor
- Search bar and pagination for Connection Manager
- `pipeline_list.js` for improved pipeline UI behavior

### Changed
- Tuned Logstash performance and stability
- Reduced the number of generated Ruby scripts created during pipeline editing
- Updated Logstash API polling behavior to be less aggressive
- Updated eviction algorithm to reduce unnecessary cache churn
- Simulation overlay now dims the interface while results are loading to prevent interaction

### Fixed
- Eliminated or significantly mitigated a Logstash memory leak caused by cached Ruby plugins
- Added a shared connection pool to prevent opening a new Logstash API connection for every request
- Removed temporary pipeline file writes during simulation
- Fixed missing return statement that caused unexpected behavior
- Simulation timeline now ignores comments
- Updated tests to reflect LogstashAgent pipeline status behavior changes

## [0.2.0] - 03/02/2026

### Added
- Toggle button for simulation that turns on/off simulation metadata
- Simulate now shows time in ms of plugin and entire execution
- Visual indicator of parsing failure / tag on failure in simulate
- Popular plugins float to the top of the plugin selector page
- Added `fs_path` type
- Added file upload for simulate when a pipeline requires it
- Comments are now supported
- Pipelines are now tested every time plugins are added/changed/removed
- Warning badge (!) appears on plugins with missing required fields
- Copy button in simulation result tooltips to copy JSON data to clipboard
- SNMP discovery workflows (tested end-to-end: discovery → device → scheduled monitoring)
- Initial implementation of the pipeline text editor
- Autocomplete, improved bracket matching, and syntax highlighting in the text editor
- Visual indicators when conditions are empty
- Save button is blocked when required fields or conditions are invalid
- SNMP test coverage improvements
- SDK-like script for interacting with the Logstash API (replaces older log analyzer)
- “Memory intensive” plugin flag with visual indicator
- `key_list_hash` type to ensure consistent grok match ordering
- Additional SNMP profiles (new + tuned existing)
- Added traps file (and related `.gitignore` updates)
- Favicon

### Changed
- Colorized the "after" JSON output for clearer visibility into changes
- Overhauled plugin configuration modal for improved usability
- View Full Event and Original Event in simulate are now more clearly clickable
- Default condition is now `if [message]`
- Migrated to Gunicorn (removed runserver + eliminated unnecessary logstashagent port)
- Updated Docker Compose configuration for 0.2.0
- Updated Nginx configuration to resolve Docker Compose issues
- Refreshed `collectstatic` workflow and removed tracking of staticfiles
- Moved pipeline renaming functionality to common module for reuse
- Adjusted Logstash configuration to optimize performance
- Simulation API endpoints now route through ConnectionManager
- Hardened and cleaned up ConnectionManager (including model updates and removal of SSH references)
- Monitoring overhaul with additional tests and refreshed static assets
- Error page overhaul and removal of public CDN calls
- Standardized on a single visualization engine
- Removed legacy Core/API layer and distributed functionality into appropriate apps
- Refactored Ruby code injection to standardize quoting and reduce escaping issues
- Cleaned up legacy JavaScript and consolidated shared utilities into `base.js`

### Fixed
- Drops no longer time out in the simulation feature
- Chevron icon when expanding advanced options in pipeline settings
- Null list values no longer insert the string `"null"` into configs
- Simulation no longer hangs when events don't match conditions (proper message shown)
- Logs no longer appear in the wrong pipeline slot
- Fixed bug when adding Elastic connections via URL after moving away from HTML-returning views
- Fixed regression with hovering over edges in the UI
- Fixed JavaScript bug using `json.dumps` instead of `JSON.stringify`
- Inline comments inside plugins no longer break parsing (inline comments are stripped to preserve round-trip stability)
- Fixed pipeline hashing issues affecting configuration load progress
- Fixed SNMP timeout/retry settings not being applied to generated configs
- Fixed profile caching confusion when pipelines were updated
- Fixed interface hover UI positioning
- Fixed incorrect pipeline count in commit toast
- Fixed bug caused by renaming SNMP data streams
- Simulation now detects success faster and gives pipelines sufficient time to complete
- Fixed race condition when simulating file-dependent plugins
- Fixed simulation file-path handling (user file paths are no longer modified)
- Updated bug report links to correct targets

## [0.1.11-12] - 02/12/2026
### Added
- Instrumented pipeline simulation
- LogstashAgent
- Containerized Logstash

## [0.1.10] - 02/12/2026
### Added
- Tests for all APIs
- User tracking for all CRUD operations
- Logging for all APIs
- CHANGELOG.md!
- Log viewer / exporter
- Clone pipeline functionality
- Added a readonly user and verification for all create/read/delete operations
- Added a cookie session age so that users aren't permanently logged in

### Changed
- Removed commented out function for simulating pipelines, will implement later
- Updated license dates
- Made the showToast function in javascript global and removed duplicated references to it in templates
- Removed CSRF_EXEMPT library because we're not using it anymore

### Fixed
- Missing grok-patterns file, preventing autocomplete in grok debugger from working
- Fixed user CRUD tests to work with new changes







