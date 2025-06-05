import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from typing_extensions import Self
from viam.components.generic import Generic
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Geometry, ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import ValueTypes, struct_to_dict
from viam.logging import getLogger

LOGGER = getLogger(__name__)

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
        
        # Required configuration attributes
        self._backport_url = None
        self._target_version = None
        self._work_dir = None
        self._platform = None
        
        # Optional configuration with safe defaults
        self._auto_install = True
        self._check_interval = 60
        self._force_reinstall = False
        self._cleanup_after_install = True
        self._restart_viam_agent = True
        
        # Computed attributes
        self._archive_name = None
        self._backup_dir = None
        self._configured = False  

        # Background task management
        self._health_check_task = None

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
        attrs = struct_to_dict(config.attributes) if config.attributes else {}
    
        # Required: Validate backport configuration
        backport_url = attrs.get("backport_url")
        if not backport_url or not isinstance(backport_url, str) or not backport_url.startswith(("http://", "https://")):
            raise ValueError("backport_url is required and must be a valid HTTP/HTTPS URL")
            
        target_version = attrs.get("target_version")
        if not target_version or not isinstance(target_version, str) or not target_version.strip():
            raise ValueError("target_version is required and must be a non-empty string")
            
        work_dir = attrs.get("work_dir")
        if not work_dir or not isinstance(work_dir, str) or not work_dir.strip():
            raise ValueError("work_dir is required and must be a non-empty string")
            
        platform = attrs.get("platform")
        if not platform or not isinstance(platform, str) or not platform.strip():
            raise ValueError("platform is required and must be a non-empty string")
            
        # Validate optional behavioral parameters
        auto_install = attrs.get("auto_install", True)
        if not isinstance(auto_install, bool):
            raise ValueError("auto_install must be a boolean")
            
        check_interval = attrs.get("check_interval", 60)
        if not isinstance(check_interval, (int, float)) or check_interval <= 0:
            raise ValueError("check_interval must be a positive number")
            
        force_reinstall = attrs.get("force_reinstall", False)
        if not isinstance(force_reinstall, bool):
            raise ValueError("force_reinstall must be a boolean")

        restart_viam_agent = attrs.get("restart_viam_agent", True)
        if not isinstance(restart_viam_agent, bool):
            raise ValueError("restart_viam_agent must be a boolean")
        
        # No dependencies required
        return [], []  

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        """Reconfigure the component with new settings."""
        attrs = struct_to_dict(config.attributes) if config.attributes else {}

        # Stop existing task before reconfiguration
        self._stop_health_check_task()
        
        # Update required configuration
        self._backport_url = attrs.get("backport_url")
        self._target_version = attrs.get("target_version")
        self._work_dir = attrs.get("work_dir")
        self._platform = attrs.get("platform")

        # Validate required fields
        if not all([self._backport_url, self._target_version, self._work_dir, self._platform]):
            self._configured = False
            LOGGER.error(f"Module {self.name} not properly configured - missing required attributes")
            LOGGER.error("Required: backport_url, target_version, work_dir, platform")
            return
        
        # Extract archive name from URL
        try:
            parsed_url = urlparse(self._backport_url)
            self._archive_name = Path(parsed_url.path).name
            if not self._archive_name:
                raise ValueError("Could not extract filename from backport_url")
        except Exception as e:
            self._configured = False
            LOGGER.error(f"Failed to extract archive name from URL: {e}")
            return
        
        # Update optional configuration with defaults
        self._auto_install = attrs.get("auto_install", True)
        self._check_interval = attrs.get("check_interval", 60)
        self._force_reinstall = attrs.get("force_reinstall", False)
        self._cleanup_after_install = attrs.get("cleanup_after_install", True)
        self._restart_viam_agent = attrs.get("restart_viam_agent", True)
        
        # Compute paths
        self._backup_dir = Path.home() / self._work_dir
        self._configured = True
        
        # Log configuration
        LOGGER.info(f"Successfully configured {self.name}")
        LOGGER.info(f"Target: {self._target_version} from {self._backport_url}")
        LOGGER.info(f"Archive: {self._archive_name}")
        LOGGER.info(f"Auto-install: {self._auto_install}, Check interval: {self._check_interval}s")
        LOGGER.info(f"Working directory: {self._backup_dir}")

        # Start background task (if auto-install is enabled)
        if self._auto_install and self._configured:
            self._start_health_check_task()

    def _start_health_check_task(self):
        """Start the background health check task."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
        
        self._health_check_task = asyncio.create_task(self._run_health_checks())
        LOGGER.info(f"Started background health check task for {self.name} (interval: {self._check_interval}s)")

    def _stop_health_check_task(self):
        """Stop the background health check task."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            LOGGER.info(f"Stopped background health check task for {self.name}")
        # Clear the task reference
        self._health_check_task = None

    async def _run_health_checks(self):
        """Background task that runs health checks at the configured interval."""
        LOGGER.info(f"Background health check started for {self.name} - first check in {self._check_interval} seconds")
        
        try:
            while True:
                try:
                    # Sleep for the specified check interval
                    await asyncio.sleep(self._check_interval)
                    
                    # Run health check
                    LOGGER.info(f"Running scheduled health check for {self.name}")
                    await self._perform_health_check()
                    
                    # Check if task was stopped during health check
                    if self._health_check_task is None or self._health_check_task.done():
                        LOGGER.info(f"Health check task stopping for {self.name}")
                        break
                    
                except asyncio.CancelledError:
                    LOGGER.info(f"Health check task cancelled for {self.name}")
                    raise
                except Exception as e:
                    LOGGER.error(f"Error during health check for {self.name}: {e}")
                    # Continue running despite errors
                    
        except asyncio.CancelledError:
            LOGGER.info(f"Background health check task stopped for {self.name}")
        except Exception as e:
            LOGGER.error(f"Fatal error in health check task for {self.name}: {e}")

    async def _perform_health_check(self):
        """Perform the actual health check and auto-install if needed."""
        try:
            # Check current status
            status = await self._check_backport_status()
            
            # Auto-install if needed
            if not status.get("is_backported", False):
                LOGGER.info(f"Auto-installing NetworkManager backport for {self.name}")
                install_result = await self._install_backport()
                
                if install_result.get("success"):
                    LOGGER.info(f"Auto-install completed successfully for {self.name}")
                    # After successful install, stop the background task
                    LOGGER.info(f"NetworkManager backport installation complete - stopping background health checks for {self.name}")
                    self._stop_health_check_task()
                else:
                    LOGGER.error(f"Auto-install failed for {self.name}: {install_result.get('error', 'Unknown error')}")
            else:
                LOGGER.debug(f"NetworkManager backport already installed for {self.name}")
                
                # Clean up leftover files if needed
                if status.get("backport_files_exist") and self._cleanup_after_install:
                    LOGGER.info(f"Cleaning up leftover installation files for {self.name}")
                    await self._cleanup_files()
                
                # Backport already installed - stop background task
                LOGGER.info(f"NetworkManager backport already installed - stopping background health checks for {self.name}")
                self._stop_health_check_task()
                    
        except Exception as e:
            LOGGER.error(f"Health check failed for {self.name}: {e}")

    async def close(self):
        """Clean up resources when the component is shut down."""
        LOGGER.info(f"Shutting down {self.name}")
        self._stop_health_check_task()
        await super().close()

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
                "backport_url": self._backport_url,
                "archive_name": self._archive_name,
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
            
            LOGGER.info(f"Starting NetworkManager backport installation for {self.name}")
            LOGGER.info(f"Target version: {self._target_version}")
            LOGGER.info(f"Platform: {self._platform}")
            
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

            # Determine overall health
            overall_health = "healthy" if service_active and backport_status.get("is_backported") else "degraded"
            
            # Check if auto-install should run
            should_auto_install = (
                self._auto_install and 
                not backport_status.get("is_backported", False)
            )

            result = {
                "overall_health": overall_health,
                "networkmanager_service_active": service_active,
                "backport_status": backport_status,
                "should_auto_install": should_auto_install,
                "background_task_running": self._health_check_task is not None and not self._health_check_task.done()
            }
            
             # Auto-install if needed (when called via do_command)
            if should_auto_install:
                LOGGER.info(f"Running auto-install via health check command for {self.name}")
                install_result = await self._install_backport()
                result["auto_install_result"] = install_result
            return result
            
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
                LOGGER.info(f"Cleaned up {self._backup_dir}")
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
                    "backport_url", "target_version", "work_dir", "platform"
                ],
            }
        
        return {
            "configured": True,
            "backport_url": self._backport_url,
            "target_version": self._target_version,
            "archive_name": self._archive_name,
            "work_dir": self._work_dir,
            "platform": self._platform,
            "auto_install": self._auto_install,
            "check_interval": self._check_interval,
            "force_reinstall": self._force_reinstall,
            "cleanup_after_install": self._cleanup_after_install,
            "restart_viam_agent": self._restart_viam_agent,
            "backup_dir": str(self._backup_dir) if self._backup_dir else None,
            "background_task_running": self._health_check_task is not None and not self._health_check_task.done()
        }

    async def _list_available_backports(self) -> Dict[str, Any]:
        """List available backports (future enhancement for discovery)."""
        return {
            "note": "This is a generic installer - configure with your specific backport details",
            "example_configurations": [
                {
                    "name": "GOST Jammy NetworkManager 1.42.8",
                    "config": {
                        "backport_url": "https://storage.googleapis.com/packages.viam.com/ubuntu/jammy-nm-backports.tar",
                        "target_version": "1.42.8",
                        "work_dir": "jammy-nm-backports",
                        "platform": "jetson-orin-nx-ubuntu-22.04"
                    }
                }
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