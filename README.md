# NetworkManager Backport Module

A generic Viam module for installing NetworkManager backports across different platforms and versions. This module enables fleet management of NetworkManager updates, with the first use case being the NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy) GOST devices that enables scanning-in-ap-mode functionality.

## Features

- **Generic Design**: Works with any NetworkManager backport following standard .deb distribution
- **Fleet Management**: Deploy via Viam fragments across entire fleet
- **Automated Detection**: Checks if backport is already installed before attempting installation
- **Health Monitoring**: Comprehensive status checking and error handling
- **Configurable**: Support for different versions, platforms, and sources
- **Idempotent**: Safe to run multiple times, only installs when needed

## Model hunter:networkmanager-backport:installer

The installer component handles downloading, extracting, and installing NetworkManager backport packages from configurable sources.

### Configuration

The following attribute template can be used to configure this model:

```json
{
  "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
  "target_version": "1.42.8",
  "archive_name": "jammy-nm-backports.tar",
  "work_dir": "nm-backports-install",
  "platform": "ubuntu-22.04",
  "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)",
  "auto_install": true,
  "force_reinstall": false,
  "cleanup_after_install": true,
  "verify_checksum": false,
  "expected_checksum": "optional-sha256-checksum"
}
```

#### Attributes

| Name | Type | Inclusion | Description |
|------|------|-----------|-------------|
| `backport_url` | string | Optional | URL to download the backport archive (defaults to GOST Jammy backport) |
| `target_version` | string | Optional | Expected NetworkManager version after backport (default: "1.42.8") |
| `archive_name` | string | Optional | Name of the archive file (default: "jammy-nm-backports.tar") |
| `work_dir` | string | Optional | Working directory for installation (default: "nm-backports-install") |
| `platform` | string | Optional | Platform identifier (default: "ubuntu-22.04") |
| `description` | string | Optional | Human-readable description of the backport |
| `auto_install` | boolean | Optional | Automatically install if backport not detected (default: true) |
| `force_reinstall` | boolean | Optional | Force reinstallation even if already installed (default: false) |
| `cleanup_after_install` | boolean | Optional | Remove downloaded files after installation (default: true) |
| `verify_checksum` | boolean | Optional | Verify archive checksum before installation (default: false) |
| `expected_checksum` | string | Required if verify_checksum=true | SHA256 checksum of the archive |

#### Example Configurations

**Basic GOST Jammy Configuration (Uses Defaults):**
```json
{
  "auto_install": true,
  "cleanup_after_install": true
}
```

**Custom Backport Configuration:**
```json
{
  "backport_url": "https://example.com/custom-nm-backports.tar",
  "target_version": "1.45.0",
  "platform": "ubuntu-24.04", 
  "description": "Custom NetworkManager 1.45.0 backport",
  "verify_checksum": true,
  "expected_checksum": "a1b2c3d4e5f6..."
}
```

**Development/Testing Configuration:**
```json
{
  "auto_install": false,
  "force_reinstall": true,
  "cleanup_after_install": false,
  "work_dir": "dev-nm-test"
}
```

### DoCommand

The installer supports the following commands via the `do_command` method:

#### check_status
Check current backport installation status.

```json
{
  "command": "check_status"
}
```

**Response:**
```json
{
  "is_backported": true,
  "current_version": "1.42.8",
  "target_version": "1.42.8", 
  "platform": "ubuntu-22.04",
  "status": "installed"
}
```

#### install_backport
Install or reinstall the NetworkManager backport.

```json
{
  "command": "install_backport"
}
```

**Response:**
```json
{
  "success": true,
  "message": "NetworkManager backport installed successfully",
  "action": "installed",
  "version": "1.42.8"
}
```

#### get_nm_version
Get current NetworkManager version.

```json
{
  "command": "get_nm_version"
}
```

#### health_check
Perform comprehensive system health check with optional auto-install.

```json
{
  "command": "health_check"
}
```

#### validate_archive
Validate the backport archive without installing.

```json
{
  "command": "validate_archive"
}
```

#### get_config
Get current module configuration.

```json
{
  "command": "get_config"
}
```

#### cleanup_files
Remove downloaded installation files.

```json
{
  "command": "cleanup"
}
```