#!/usr/bin/env python3
"""
NetworkManager Backport Installer

A generic Viam component for installing NetworkManager backports across different
platforms and versions. Supports fleet management and automated deployment.
"""

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple

from typing_extensions import Self
from viam.components.generic import Generic
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Geometry, ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import ValueTypes, struct_to_dict

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


class Installer(Generic, EasyResource):
    """
    A Viam Generic component that manages NetworkManager backport installation
    across different platforms and versions. Supports any NetworkManager backport
    that follows the standard .deb package distribution pattern.
    """
    
    MODEL: ClassVar[Model] = Model(
        ModelFamily("hunter", "networkmanager-backport"), 
        "installer"
    )
    
    # Default configuration for the original GOST Jammy backport
    DEFAULT_CONFIG = {
        "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
        "target_version": "1.42.8",
        "archive_name": "jammy-nm-backports.tar",
        "work_dir": "nm-backports-install",
        "platform": "ubuntu-22.04",
        "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)"
    }

    def __init__(self, name: str):
        super().__init__(name)
        
        # Configuration attributes (will be set via reconfigure)
        self._backport_url = self.DEFAULT_CONFIG["backport_url"]
        self._target_version = self.DEFAULT_CONFIG["target_version"]
        self._archive_name = self.DEFAULT_CONFIG["archive_name"]
        self._work_dir = self.DEFAULT_CONFIG["work_dir"]
        self._platform = self.DEFAULT_CONFIG["platform"]
        self._description = self.DEFAULT_CONFIG["description"]
        
        # Behavioral configuration
        self._auto_install = True
        self._check_interval = 3600  # Check every hour by default
        self._force_reinstall = False
        self._cleanup_after_install = True
        self._verify_checksum = False
        self._expected_checksum = None
        
        # Computed paths (updated when config changes)
        self._backup_dir = Path.home() / self._work_dir

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        """Create a new NetworkManager Backport Installer instance from config."""
        instance = cls(config.name)
        instance.reconfigure(config, dependencies)
        return instance

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """Validate the component configuration."""
        # Convert config attributes to dict for easier access
        attrs = struct_to_dict(config.attributes) if config.attributes else {}
        
        # Validate required backport configuration
        backport_url = attrs.get("backport_url", cls.DEFAULT_CONFIG["backport_url"])
        if not isinstance(backport_url, str) or not backport_url.startswith(("http://", "https://")):
            raise ValueError("backport_url must be a valid HTTP/HTTPS URL")
            
        target_version = attrs.get("target_version", cls.DEFAULT_CONFIG["target_version"])
        if not isinstance(target_version, str) or not target_version.strip():
            raise ValueError("target_version must be a non-empty string")
            
        # Validate optional configuration
        archive_name = attrs.get("archive_name", cls.DEFAULT_CONFIG["archive_name"])
        if not isinstance(archive_name, str) or not archive_name.strip():
            raise ValueError("archive_name must be a non-empty string")
            
        work_dir = attrs.get("work_dir", cls.DEFAULT_CONFIG["work_dir"])
        if not isinstance(work_dir, str) or not work_dir.strip():
            raise ValueError("work_dir must be a non-empty string")
            
        # Validate behavioral parameters
        auto_install = attrs.get("auto_install", True)
        if not isinstance(auto_install, bool):
            raise ValueError("auto_install must be a boolean")
            
        check_interval = attrs.get("check_interval", 3600)
        if not isinstance(check_interval, (int, float)) or check_interval <= 0:
            raise ValueError("check_interval must be a positive number")
            
        force_reinstall = attrs.get("force_reinstall", False)
        if not isinstance(force_reinstall, bool):
            raise ValueError("force_reinstall must be a boolean")
            
        verify_checksum = attrs.get("verify_checksum", False)
        if not isinstance(verify_checksum, bool):
            raise ValueError("verify_checksum must be a boolean")
            
        # If checksum verification is enabled, checksum must be provided
        if verify_checksum:
            expected_checksum = attrs.get("expected_checksum")
            if not expected_checksum or not isinstance(expected_checksum, str):
                raise ValueError("expected_checksum must be provided when verify_checksum is true")
        
        return [], []  # No dependencies required

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        """Reconfigure the component with new settings."""
        attrs = struct_to_dict(config.attributes) if config.attributes else {}
        
        # Update backport configuration
        self._backport_url = attrs.get("backport_url", self.DEFAULT_CONFIG["backport_url"])
        self._target_version = attrs.get("target_version", self.DEFAULT_CONFIG["target_version"])
        self._archive_name = attrs.get("archive_name", self.DEFAULT_CONFIG["archive_name"])
        self._work_dir = attrs.get("work_dir", self.DEFAULT_CONFIG["work_dir"])
        self._platform = attrs.get("platform", self.DEFAULT_CONFIG["platform"])
        self._description = attrs.get("description", self.DEFAULT_CONFIG["description"])
        
        # Update behavioral configuration
        self._auto_install = attrs.get("auto_install", True)
        self._check_interval = attrs.get("check_interval", 3600)
        self._force_reinstall = attrs.get("force_reinstall", False)
        self._cleanup_after_install = attrs.get("cleanup_after_install", True)
        self._verify_checksum = attrs.get("verify_checksum", False)
        self._expected_checksum = attrs.get("expected_checksum", None)
        
        # Update computed paths
        self._backup_dir = Path.home() / self._work_dir
        
        self.logger.info(f"Reconfigured {self.name} for {self._description}")
        self.logger.info(f"Target: {self._target_version} from {self._backport_url}")
        self.logger.info(f"Auto-install: {self._auto_install}, Force: {self._force_reinstall}")

    async def do_command(
        self,
        command: Mapping[str, ValueTypes],
        *,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Mapping[str, ValueTypes]:
        """Handle custom commands for the NetworkManager backport installer."""
        cmd = command.get("command", "")
        
        if cmd == "check_status":
            return await self._check_backport_status()
        elif cmd == "install_backport":
            return await self._install_backport()
        elif cmd == "get_nm_version":
            return await self._get_networkmanager_version()
        elif cmd == "get_config":
            return self._get_current_config()
        elif cmd == "list_backports":
            return await self._list_available_backports()
        elif cmd == "validate_archive":
            return await self._validate_archive()
        elif cmd == "health_check":
            return await self._health_check()
        elif cmd == "cleanup_files":
            return await self._cleanup_files()
        else:
            return {
                "error": f"Unknown command: {cmd}",
                "available_commands": [
                    "check_status", "install_backport", "get_nm_version", 
                    "get_config", "list_backports", "validate_archive",
                    "health_check", "cleanup_files"
                ]
            }

    async def get_geometries(
        self, *, extra: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None
    ) -> List[Geometry]:
        """Return empty geometries as this is a software component."""
        return []

    async def _check_backport_status(self) -> Dict[str, Any]:
        """Check if the NetworkManager backport has been applied."""
        try:
            # Get current NetworkManager version
            result = await self._run_command(["NetworkManager", "--version"])
            current_version = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            # Check if target version is installed
            is_backported = self._target_version in current_version
            
            # Check if backport files exist
            backport_files_exist = self._backup_dir.exists() and any(
                self._backup_dir.glob("*.deb")
            )
            
            return {
                "is_backported": is_backported,
                "current_version": current_version,
                "target_version": self._target_version,
                "backport_files_exist": backport_files_exist,
                "auto_install_enabled": self._auto_install,
                "platform": self._platform,
                "description": self._description,
                "backport_url": self._backport_url,
                "status": "installed" if is_backported else "needs_install"
            }
        except Exception as e:
            self.logger.error(f"Error checking backport status: {e}")
            return {
                "error": str(e),
                "status": "error"
            }

    async def _install_backport(self) -> Dict[str, Any]:
        """Install the NetworkManager backport."""
        try:
            # Check if already installed and not forcing reinstall
            status = await self._check_backport_status()
            if status.get("is_backported") and not self._force_reinstall:
                return {
                    "success": True,
                    "message": "NetworkManager backport already installed",
                    "action": "skipped",
                    "version": status.get("current_version")
                }
            
            self.logger.info("Starting NetworkManager backport installation...")
            self.logger.info(f"Installing {self._description}")
            self.logger.info(f"Target version: {self._target_version}")
            
            # Create backup directory
            self._backup_dir.mkdir(exist_ok=True)
            
            # Download backport archive
            archive_path = self._backup_dir / self._archive_name
            self.logger.info(f"Downloading backport from {self._backport_url}")
            download_result = await self._run_command([
                "curl", "-fsSL", self._backport_url, 
                "-o", str(archive_path)
            ])
            
            if download_result.returncode != 0:
                raise Exception(f"Failed to download backport: {download_result.stderr}")
            
            # Verify checksum if configured
            if self._verify_checksum and self._expected_checksum:
                if not await self._verify_file_checksum(archive_path):
                    raise Exception("Archive checksum verification failed")
            
            # Extract archive
            self.logger.info("Extracting backport archive...")
            extract_result = await self._run_command([
                "tar", "-xvf", self._archive_name
            ], cwd=str(self._backup_dir))
            
            if extract_result.returncode != 0:
                raise Exception(f"Failed to extract archive: {extract_result.stderr}")
            
            # Install .deb packages
            self.logger.info("Installing .deb packages...")
            deb_files = list(self._backup_dir.glob("*.deb"))
            if not deb_files:
                raise Exception("No .deb files found in extracted archive")
            
            install_result = await self._run_command([
                "sudo", "dpkg", "-i"
            ] + [str(f) for f in deb_files])
            
            if install_result.returncode != 0:
                # Try to fix broken dependencies
                self.logger.warning("dpkg install failed, attempting to fix dependencies...")
                fix_result = await self._run_command(["sudo", "apt-get", "install", "-f", "-y"])
                if fix_result.returncode != 0:
                    raise Exception(f"Failed to install packages: {install_result.stderr}")
            
            # Restart NetworkManager service
            self.logger.info("Restarting NetworkManager service...")
            restart_result = await self._run_command([
                "sudo", "systemctl", "restart", "NetworkManager"
            ])
            
            if restart_result.returncode != 0:
                self.logger.warning(f"Failed to restart NetworkManager: {restart_result.stderr}")
            
            # Cleanup if requested
            if self._cleanup_after_install:
                await self._cleanup_files()
            
            # Verify installation
            final_status = await self._check_backport_status()
            
            return {
                "success": True,
                "message": "NetworkManager backport installed successfully",
                "action": "installed",
                "version": final_status.get("current_version"),
                "is_backported": final_status.get("is_backported", False)
            }
            
        except Exception as e:
            self.logger.error(f"Error installing backport: {e}")
            return {
                "success": False,
                "error": str(e),
                "action": "failed"
            }

    async def _get_networkmanager_version(self) -> Dict[str, Any]:
        """Get the current NetworkManager version."""
        try:
            result = await self._run_command(["NetworkManager", "--version"])
            if result.returncode == 0:
                version = result.stdout.strip()
                return {
                    "version": version,
                    "is_target_version": self._target_version in version
                }
            else:
                return {
                    "error": "Failed to get NetworkManager version",
                    "stderr": result.stderr
                }
        except Exception as e:
            return {"error": str(e)}

    async def _health_check(self) -> Dict[str, Any]:
        """Perform a comprehensive health check."""
        try:
            # Check NetworkManager service status
            service_result = await self._run_command([
                "systemctl", "is-active", "NetworkManager"
            ])
            
            service_active = service_result.returncode == 0
            
            # Check backport status
            backport_status = await self._check_backport_status()
            
            # Check if auto-install should run
            should_auto_install = (
                self._auto_install and 
                not backport_status.get("is_backported", False)
            )
            
            health_status = {
                "overall_health": "healthy" if service_active and backport_status.get("is_backported") else "degraded",
                "networkmanager_service_active": service_active,
                "backport_status": backport_status,
                "should_auto_install": should_auto_install,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            # Auto-install if configured and needed
            if should_auto_install:
                self.logger.info("Auto-installing NetworkManager backport...")
                install_result = await self._install_backport()
                health_status["auto_install_result"] = install_result
            
            return health_status
            
        except Exception as e:
            return {
                "overall_health": "error",
                "error": str(e)
            }

    async def _cleanup_files(self) -> Dict[str, Any]:
        """Clean up downloaded backport files."""
        try:
            if self._backup_dir.exists():
                shutil.rmtree(self._backup_dir)
                return {
                    "success": True,
                    "message": f"Cleaned up {self._backup_dir}"
                }
            else:
                return {
                    "success": True,
                    "message": "No files to clean up"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _get_current_config(self) -> Dict[str, Any]:
        """Get the current module configuration."""
        return {
            "backport_url": self._backport_url,
            "target_version": self._target_version,
            "archive_name": self._archive_name,
            "work_dir": self._work_dir,
            "platform": self._platform,
            "description": self._description,
            "auto_install": self._auto_install,
            "check_interval": self._check_interval,
            "force_reinstall": self._force_reinstall,
            "cleanup_after_install": self._cleanup_after_install,
            "verify_checksum": self._verify_checksum,
            "backup_dir": str(self._backup_dir)
        }

    async def _list_available_backports(self) -> Dict[str, Any]:
        """List available backports (future enhancement for discovery)."""
        # This is a placeholder for future functionality
        # Could query a registry or known locations for available backports
        return {
            "available_backports": [
                {
                    "version": "1.42.8",
                    "platform": "ubuntu-22.04",
                    "url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
                    "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)",
                    "features": ["scanning-in-ap-mode"]
                }
                # Future: could dynamically discover more backports
            ],
            "current_config": {
                "target_version": self._target_version,
                "platform": self._platform
            }
        }

    async def _validate_archive(self) -> Dict[str, Any]:
        """Validate the configured backport archive without installing."""
        try:
            # Create temporary directory for validation
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                archive_path = temp_path / self._archive_name
                
                # Download archive
                download_result = await self._run_command([
                    "curl", "-fsSL", self._backport_url, 
                    "-o", str(archive_path)
                ])
                
                if download_result.returncode != 0:
                    return {
                        "valid": False,
                        "error": f"Failed to download: {download_result.stderr}"
                    }
                
                # Verify checksum if configured
                if self._verify_checksum and self._expected_checksum:
                    if not await self._verify_file_checksum(archive_path):
                        return {
                            "valid": False,
                            "error": "Checksum verification failed"
                        }
                
                # Extract and examine contents
                extract_result = await self._run_command([
                    "tar", "-tf", self._archive_name
                ], cwd=str(temp_path))
                
                if extract_result.returncode != 0:
                    return {
                        "valid": False,
                        "error": f"Failed to examine archive: {extract_result.stderr}"
                    }
                
                # Check for .deb files in listing
                file_list = extract_result.stdout.strip().split('\n')
                deb_files = [f for f in file_list if f.endswith('.deb')]
                
                return {
                    "valid": True,
                    "archive_size": archive_path.stat().st_size,
                    "file_count": len(file_list),
                    "deb_files": deb_files,
                    "deb_count": len(deb_files),
                    "all_files": file_list
                }
                
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }

    async def _verify_file_checksum(self, file_path: Path) -> bool:
        """Verify file checksum if checksum verification is enabled."""
        try:
            # Calculate SHA256 checksum
            result = await self._run_command(["sha256sum", str(file_path)])
            if result.returncode != 0:
                self.logger.error(f"Failed to calculate checksum: {result.stderr}")
                return False
            
            calculated_checksum = result.stdout.split()[0]
            return calculated_checksum.lower() == self._expected_checksum.lower()
            
        except Exception as e:
            self.logger.error(f"Checksum verification failed: {e}")
            return False

    async def _run_command(self, cmd: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run a shell command asynchronously."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        stdout, stderr = await process.communicate()
        
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else ""
        )