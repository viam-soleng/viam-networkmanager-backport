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
    
    def __init__(self, name: str):
        super().__init__(name)
        
        # Configuration attributes
        # MUST set via reconfigure
        self._backport_url = None
        self._target_version = None
        self._archive_name = None
        self._work_dir = None
        self._platform = None
        self._description = None
        
        # Configuration with safe defaults
        self._auto_install = False
        self._check_interval = 3600
        self._force_reinstall = False
        self._cleanup_after_install = True
        self._verify_checksum = False
        self._expected_checksum = None
        self._restart_viam_agent = True
        
        # Computed paths
        # Set after reconfigure
        self._backup_dir = None
        # Track if properly configured
        self._configured = False  

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
        
        # REQUIRED: Validate all essential backport configuration
        backport_url = attrs.get("backport_url")
        if not backport_url or not isinstance(backport_url, str) or not backport_url.startswith(("http://", "https://")):
            raise ValueError("backport_url is required and must be a valid HTTP/HTTPS URL")
            
        target_version = attrs.get("target_version")
        if not target_version or not isinstance(target_version, str) or not target_version.strip():
            raise ValueError("target_version is required and must be a non-empty string")
            
        archive_name = attrs.get("archive_name")
        if not archive_name or not isinstance(archive_name, str) or not archive_name.strip():
            raise ValueError("archive_name is required and must be a non-empty string")
            
        work_dir = attrs.get("work_dir")
        if not work_dir or not isinstance(work_dir, str) or not work_dir.strip():
            raise ValueError("work_dir is required and must be a non-empty string")
            
        platform = attrs.get("platform")
        if not platform or not isinstance(platform, str) or not platform.strip():
            raise ValueError("platform is required and must be a non-empty string")
        
        description = attrs.get("description")
        if not description or not isinstance(description, str) or not description.strip():
            raise ValueError("description is required and must be a non-empty string")
            
        # Validate behavioral parameters
        auto_install = attrs.get("auto_install", False)
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

        restart_viam_agent = attrs.get("restart_viam_agent", True)
        if not isinstance(restart_viam_agent, bool):
            raise ValueError("restart_viam_agent must be a boolean")
            
        # If checksum verification is enabled, then checksum MUST be provided!
        if verify_checksum:
            expected_checksum = attrs.get("expected_checksum")
            if not expected_checksum or not isinstance(expected_checksum, str):
                raise ValueError("expected_checksum must be provided when verify_checksum is true")
        
        # No dependencies required
        return [], []  

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        """Reconfigure the component with new settings."""
        attrs = struct_to_dict(config.attributes) if config.attributes else {}
        
        # Update REQUIRED backport configuration
        # No defaults
        self._backport_url = attrs.get("backport_url")
        self._target_version = attrs.get("target_version")
        self._archive_name = attrs.get("archive_name")
        self._work_dir = attrs.get("work_dir")
        self._platform = attrs.get("platform")
        self._description = attrs.get("description")
        
        # Validate all required fields are present
        if not all([self._backport_url, self._target_version, self._archive_name, 
                   self._work_dir, self._platform, self._description]):
            self._configured = False
            LOGGER.error(f"Module {self.name} not properly configured - missing required attributes")
            LOGGER.error("Required: backport_url, target_version, archive_name, work_dir, platform, description")
            return
        
        # Update behavioral configuration with safe defaults
        self._auto_install = attrs.get("auto_install", False)
        self._check_interval = attrs.get("check_interval", 3600)
        self._force_reinstall = attrs.get("force_reinstall", False)
        self._cleanup_after_install = attrs.get("cleanup_after_install", True)
        self._verify_checksum = attrs.get("verify_checksum", False)
        self._expected_checksum = attrs.get("expected_checksum", None)
        self._restart_viam_agent = attrs.get("restart_viam_agent", True)
        
        # Update computed paths
        self._backup_dir = Path.home() / self._work_dir
        self._configured = True
        
        LOGGER.info(f"Successfully configured {self.name}")
        LOGGER.info(f"Description: {self._description}")
        LOGGER.info(f"Target: {self._target_version} from {self._backport_url}")
        LOGGER.info(f"Auto-install: {self._auto_install}, Force: {self._force_reinstall}")
        LOGGER.info(f"Working directory: {self._backup_dir}")

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
            LOGGER.error(f"Error checking backport status: {e}")
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
            
            LOGGER.info("Starting NetworkManager backport installation...")
            LOGGER.info(f"Installing {self._description}")
            LOGGER.info(f"Target version: {self._target_version}")
            
            # Create backup directory
            self._backup_dir.mkdir(exist_ok=True)
            
            # Download backport archive
            archive_path = self._backup_dir / self._archive_name
            LOGGER.info(f"Downloading backport from {self._backport_url}")
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
            LOGGER.info("Extracting backport archive...")
            extract_result = await self._run_command([
                "tar", "-xvf", self._archive_name
            ], cwd=str(self._backup_dir))
            
            if extract_result.returncode != 0:
                raise Exception(f"Failed to extract archive: {extract_result.stderr}")
            
            # Install .deb packages
            LOGGER.info("Installing .deb packages...")
            deb_files = list(self._backup_dir.glob("*.deb"))
            if not deb_files:
                raise Exception("No .deb files found in extracted archive")
            
            install_result = await self._run_command([
                "sudo", "dpkg", "-i"
            ] + [str(f) for f in deb_files])
            
            if install_result.returncode != 0:
                # Try to fix broken dependencies
                LOGGER.warning(f"dpkg install failed for {self.name}, attempting to fix dependencies")
                fix_result = await self._run_command(["sudo", "apt-get", "install", "-f", "-y"])
                if fix_result.returncode != 0:
                    raise Exception(f"Failed to install packages: {install_result.stderr}")
            
            # Restart NetworkManager service
            LOGGER.info("Restarting NetworkManager service...")
            restart_result = await self._run_command([
                "sudo", "systemctl", "restart", "NetworkManager"
            ])
            
            if restart_result.returncode != 0:
                LOGGER.warning(f"Failed to restart NetworkManager for {self.name}: {restart_result.stderr}")
            else:
                # Wait for NetworkManager to fully initialize
                LOGGER.info(f"NetworkManager restarted successfully for {self.name}, waiting for initialization...")
                await asyncio.sleep(10)

                # Check if NetworkManager is properly running
                status_check = await self._run_command(["systemctl", "is-active", "NetworkManager"])
                
                if status_check.returncode == 0:
                    # Restart viam-agent to re-initialize network interfaces (if enabled)
                    if self._restart_viam_agent:
                        LOGGER.info(f"Restarting viam-agent for {self.name} to refresh network interfaces...")
                        agent_restart = await self._run_command([
                            "sudo", "systemctl", "restart", "viam-agent"
                        ])

                        if agent_restart.returncode == 0:
                            LOGGER.info(f"viam-agent restarted successfully for {self.name}")

                            # Wait for viam-agent to come back online...
                            await asyncio.sleep(30)

                        else:
                            LOGGER.warning(f"Failed to restart viam-agent for {self.name}: {agent_restart.stderr}")

                    else:
                        LOGGER.info(f"viam-agent restart disabled for {self.name}")

                else:
                    LOGGER.error(f"NetworkManager failed to start properly for {self.name}")
            
            # Cleanup files (if configured)
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
            LOGGER.error(f"Error installing backport for {self.name}: {e}")
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
                LOGGER.info(f"Auto-installing NetworkManager backport for {self.name}")
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
        if not self._configured:
            return {
                "configured": False,
                "error": "Module not properly configured",
                "required_attributes": [
                    "backport_url", "target_version", "archive_name", 
                    "work_dir", "platform", "description"
                ],
                "example_config": {
                    "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
                    "target_version": "1.42.8",
                    "archive_name": "jammy-nm-backports.tar",
                    "work_dir": "nm-backports-install",
                    "platform": "ubuntu-22.04",
                    "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)"
                }
            }
        
        return {
            "configured": True,
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
            "restart_viam_agent": self._restart_viam_agent,
            "backup_dir": str(self._backup_dir) if self._backup_dir else None
        }

    async def _list_available_backports(self) -> Dict[str, Any]:
        """List available backports (future enhancement for discovery)."""
        # This is a placeholder for future functionality
        # Could query a registry or known locations for available backports
        return {
            "note": "This is a generic installer - configure with your specific backport details",
            "example_configurations": [
                {
                    "name": "GOST Jammy NetworkManager 1.42.8",
                    "config": {
                        "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
                        "target_version": "1.42.8",
                        "archive_name": "jammy-nm-backports.tar",
                        "work_dir": "jammy-nm-backports",
                        "platform": "ubuntu-22.04",
                        "description": "NetworkManager 1.42.8 backport for Ubuntu 22.04 (Jammy)"
                    }
                }
                # Future: could dynamically discover more backports
            ],
            "current_config": {
                "configured": self._configured,
                "target_version": self._target_version if self._configured else None,
                "platform": self._platform if self._configured else None
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
                LOGGER.error(f"Failed to calculate checksum for {self.name}: {result.stderr}")
                return False
            
            calculated_checksum = result.stdout.split()[0]
            return calculated_checksum.lower() == self._expected_checksum.lower()
            
        except Exception as e:
            LOGGER.error(f"Checksum verification failed for {self.name}: {e}")
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