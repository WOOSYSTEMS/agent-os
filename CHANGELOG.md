# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure
- Design document with full architecture
- Development roadmap
- README and documentation
- Apache 2.0 license

### Changed
- N/A

### Fixed
- N/A

---

## [0.1.0-alpha.2] - 2025-12-15

### Added
- **Memory Manager** with four scopes:
  - Context: Ephemeral, current task only
  - Working: Session state, cleared on restart
  - Long-term: Persistent storage via SQLite
  - Shared: Accessible by multiple agents
- **Message Bus** for inter-agent communication:
  - Point-to-point messaging
  - Request/response patterns with timeout
  - Event broadcasting with subscriptions
  - Wildcard event subscriptions
- Runtime statistics endpoint
- Phase 2 test suite

### Changed
- Runtime now initializes memory and messaging on start
- Agents registered with message bus on spawn
- Agent termination cleans up memory and messaging

---

## [0.1.0-alpha.1] - 2025-12-15

### Added
- Core agent runtime
- Basic tool system (shell, file, http)
- Simple capability checking
- CLI interface

---

*Template for future releases:*

## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Features to be removed in future versions

### Removed
- Features removed in this version

### Fixed
- Bug fixes

### Security
- Security-related changes
