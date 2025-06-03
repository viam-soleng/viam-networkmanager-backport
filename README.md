# NetworkManager Backport Module

A Viam module for installing NetworkManager backports across device fleets.

## Model hunter:networkmanager-backport:installer

The installer component handles downloading, extracting, and installing NetworkManager backport packages from configurable sources.

### Configuration

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

| Name | Type | Description |
|------|------|-----------|
| `backport_url` | string | URL to download the backport archive |
| `target_version` | string | Expected NetworkManager version after backport |
| `archive_name` | string | Name of the archive file |
| `work_dir` | string | Working directory for installation |
| `platform` | string | Platform identifier (e.g., "ubuntu-22.04") |
| `description` | string | Human-readable description of the backport |

#### Optional Attributes

| Name | Type | Default | Description |
|------|------|-----------|-------------|
| `auto_install` | boolean | false | Automatically install if backport not detected |
| `check_interval` | integer | 3600 | Seconds between health checks |
| `force_reinstall` | boolean | false | Force reinstallation even if already installed |
| `cleanup_after_install` | boolean | true | Remove downloaded files after installation |
| `restart_viam_agent` | boolean | true | Restart viam-agent after NetworkManager restart |
| `verify_checksum` | boolean | false | Verify archive checksum before installation |
| `expected_checksum` | string | null | SHA256 checksum (required if verify_checksum=true) |

### Installation Process

When auto-install is triggered, the module follows this sequence:
1. **Download**: Retrieves backport archive from configured URL
2. **Verify**: Checks SHA256 checksum (if enabled)
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