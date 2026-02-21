## [0.1.13] - TBD
### Added
- Toggle button for simulation that turns on/off simulation metadat
- Simulate now shows time in ms of plugin and entire execution
- Visual indicator of parsing failure / tag on failure in simulate
- Popular plugins float to the top of the plugin selector page
- Added fs_path type
- Added file upload for simulate when a pipeline requires it

### Changed
- Colorized the "after" json output to be more readable and clearly convey what was changed


### Fixed
- Drops no longer time out in the simulation feature
- Chevron icon when expanding advanced options in pipeline settings

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







