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







