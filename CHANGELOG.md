## [0.1.10] - TBD
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







