## [0.1.13] - TBD
### Added
- Toggle button for simulation that turns on/off simulation metadat
- Simulate now shows time in ms of plugin and entire execution
- Visual indicator of parsing failure / tag on failure in simulate
- Popular plugins float to the top of the plugin selector page
- Added fs_path type
- Added file upload for simulate when a pipeline requires it
- Comments are now supported!
- Pipelines are now tested every time plugins are added/changed/removed
- Warning badge (!) appears on plugins with missing required fields
- Copy button in simulation result tooltips to copy JSON data to clipboard
- Discovery for SNMP - Tested the end-to-end process of discovery and adding a device
- Added initial implementation of the text editor

### Changed
- Colorized the "after" json output to be more readable and clearly convey what was changed
- Overhaul of plugin config modal to be more user friendly
- View Full Event and Original Event in the editor during a simulate is more obviously clickable
- Default condition is now 'if [message]'

### Fixed
- Drops no longer time out in the simulation feature
- Chevron icon when expanding advanced options in pipeline settings
- Bug that caused null lists to be inserted into the list
- Simulation no longer hangs when events don't match any conditions (shows proper message instead)
- Logs showing up in the wrong pipeline's error logs because they shared the same slot

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







