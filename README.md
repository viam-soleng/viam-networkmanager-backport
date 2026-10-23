# NetworkManager Backport Module

A Viam module for installing NetworkManager backports across device fleets.

## Why this module exists

The GOST mobile app (`gost-mobile-app`) provisions Specter AI devices over a WiFi hotspot. When a device has no known network, viam-agent starts a `gost`-prefixed hotspot. The phone joins it, the app asks the device for the WiFi networks it can see, and the user picks one and enters the password. This only works if the device can scan for networks while its hotspot is running. Jetsons on Ubuntu 22.04 ship NetworkManager 1.36.x (1.36.4 at release, 1.36.6 in jammy-updates), and on those devices scanning in hotspot mode fails. After three failed scans, viam-agent turns off scanning while in hotspot mode ("Device hardware/software does not appear to support wifi scanning while hotspot is active"). The app then shows an empty network list, and provisioning is not likely to succeed. To fix this, the agent team built NetworkManager 1.42.8 for Jammy arm64 (`jammy-nm-backports.tar`, May 2025). This module installs that build on the preload. It checks the installed NetworkManager version, installs the 1.42.8 packages if needed, restarts NetworkManager, and restarts viam-agent so the networking subsystem picks up the new NetworkManager. Note that viam-agent itself only requires NetworkManager 1.30 or newer. The 1.42.8 backport is what the GOST app's hotspot provisioning flow needs.

## Model viam-soleng:networkmanager-backport:installer

The installer component handles downloading, extracting, and installing NetworkManager backport packages from configurable sources.

### Configuration

```json
{
  "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
  "target_version": "1.42.8",
  "work_dir": "jammy-nm-backports",
  "platform": "jetson-orin-nx-ubuntu-22.04",
  "auto_install": true,
  "check_interval": 60,
  "cleanup_after_install": true,
  "restart_viam_agent": true,
  "force_reinstall": false
}
```

#### Required Attributes

| Name | Type | Description |
|------|------|-----------|
| `backport_url` | string | URL to download the backport archive |
| `target_version` | string | Expected NetworkManager version after backport |
| `work_dir` | string | Working directory for installation |
| `platform` | string | Platform identifier (e.g., "ubuntu-22.04") |

#### Optional Attributes

| Name | Type | Default | Description |
|------|------|-----------|-------------|
| `auto_install` | boolean | false | Automatically install if backport not detected |
| `check_interval` | integer | 3600 | Seconds between health checks |
| `cleanup_after_install` | boolean | true | Remove downloaded files after installation |
| `restart_viam_agent` | boolean | true | Restart viam-agent after NetworkManager restart |
| `force_reinstall` | boolean | false | Force reinstallation even if already installed |

### Installation Process

When auto-install is triggered, the module follows this sequence:
1. **Download**: Retrieves backport archive from configured URL
3. **Extract**: Unpacks .deb packages from archive
4. **Install**: Uses `dpkg -i` to install packages, with automatic dependency fixing
5. **Restart NetworkManager**: Restarts service and waits for initialization
6. **Restart viam-agent**:  Restarts agent to refresh network interfaces (if enabled)
7. **Cleanup**: Removes installation files (if enabled)
8. **Shutdown**: Stops background health check task

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
  "archive_name": "jammy-nm-backports.tar",
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
  "platform": "jetson-orin-nx-ubuntu-22.04",
  "archive_name": "jammy-nm-backports.tar"
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