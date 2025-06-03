# NetworkManager Backport Module

A generic Viam module for installing NetworkManager backports across different platforms and versions. This module enables fleet management of NetworkManager updates with automatic installation.

## Features
- **Generic Design**: Works with any NetworkManager backport following standard .deb distribution
- **Fleet Management**: Deploy via Viam fragments across entire fleet
- **Automated Installation**: Automatically installs on startup, then stops background tasks
- **Automated Detection**: Checks if backport is already installed before attempting installation
- **Health Monitoring**: Comprehensive status checking and error handling
- **Configurable**: Support for different versions, platforms, and sources
- **Idempotent**: Safe to run multiple times, only installs when needed
- **Self-Cleaning**: Automatically removes installation files after completion

## Model hunter:networkmanager-backport:installer

The installer component handles downloading, extracting, and installing NetworkManager backport packages from configurable sources with smart lifecycle management.

### Behavior

1. **Startup**: Module configures and starts background health check task (if auto_install: true)
2. **First Check**: Runs after check_interval seconds, detects if backport needed
3. **Auto-Install**: Downloads, installs, and configures NetworkManager backport automatically
4. **Smart Shutdown**: Stops background tasks after successful installation to save resources
5. **Cleanup**: Removes installation files automatically (if cleanup_after_install: true)

### Configuration

**⚠️ IMPORTANT: All configuration attributes are REQUIRED for safety.**

The module requires explicit configuration to prevent accidental system modifications.

```json
{
  "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
  "target_version": "1.42.8",
  "archive_name": "jammy-nm-backports.tar",
  "work_dir": "jammy-nm-backports",
  "platform": "jetson-orin-nx-ubuntu-22.04",
  "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)",
  "auto_install": true,
  "cleanup_after_install": true,
  "restart_viam_agent": true,
  "check_interval": 60
}
```

#### Required Attributes

| Name | Type | Inclusion | Description |
|------|------|-----------|-------------|
| `backport_url` | string | **REQUIRED** | URL to download the backport archive |
| `target_version` | string | **REQUIRED** | Expected NetworkManager version after backport |
| `archive_name` | string | **REQUIRED** | Name of the archive file |
| `work_dir` | string | **REQUIRED** | Working directory for installation |
| `platform` | string | **REQUIRED** | Platform identifier (e.g., "ubuntu-22.04") |
| `description` | string | **REQUIRED** | Human-readable description of the backport |



| `force_reinstall` | boolean | Optional | Force reinstallation even if already installed (default: false) |
| `cleanup_after_install` | boolean | Optional | Remove downloaded files after installation (default: true) |
| `verify_checksum` | boolean | Optional | Verify archive checksum before installation (default: false) |
| `expected_checksum` | string | Required if verify_checksum=true | SHA256 checksum of the archive |

#### Optional Attributes

| Name | Type | Inclusion | Description |
|------|------|-----------|-------------|
| `auto_install` | boolean | Optional | Automatically install if backport not detected (default: false) |
| `check_interval` | number | Optional | Automatically install if backport not detected (default: false) |

### Installation Process

When auto-install is triggered, the module follow this sequence:
1. **Download**: Retrieves backport archive from configured URL
2. **Verify**: Checks SHA256 checksum if configured
3. **Extract**: Unpacks .deb packages from archive
4. **Install**: Uses `dpkg -i` to install packages, with automatic dependency fixing
5. **Restart NetworkManager**: Restarts service and waits for initialization
6. **Restart viam-agent**:  Restarts agent to refresh network interfaces (if enabled)
7. **Cleanup**: Removes installation files (if enabled)
8. **Shutdown**: Stops background health check task to save resources


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
  "status": "installed",
  "is_backported": true,
  "current_version": "1.42.8",
  "target_version": "1.42.8",
  "platform": "jetson-orin-nx-ubuntu-22.04",
  "auto_install_enabled": true,
  "backport_files_exist": false,
  "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)",
  "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar"
}
```

#### install_backport
Manually install or reinstall the NetworkManager backport.

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
  "version": "1.42.8",
  "is_backported": true
}
```

#### get_nm_version
Get current NetworkManager version.

```json
{
  "command": "get_nm_version"
}
```

**Response**:
```json
{
  "version": "1.42.8",
  "is_target_version": true
}
```


#### health_check
Perform comprehensive system health check with optional auto-install.

```json
{
  "command": "health_check"
}
```

**Response**:
```json
{
  "overall_health": "healthy",
  "networkmanager_service_active": true,
  "should_auto_install": false,
  "background_task_running": false,
  "backport_status": { ... }
}
```

#### get_config
Get current module configuration and status.

```json
{
  "command": "get_config"
}
```

**Response**:
```json
{
  "configured": true,
  "auto_install": true,
  "check_interval": 60,
  "background_task_running": false,
  "backup_dir": "/root/jammy-nm-backports",
  "target_version": "1.42.8",
  "platform": "jetson-orin-nx-ubuntu-22.04"
}
```

#### validate_archive
Validate the backport archive without installing.

```json
{
  "command": "validate_archive"
}
```

#### cleanup_files
Remove downloaded installation files.

```json
{
  "command": "cleanup_files"
}
```