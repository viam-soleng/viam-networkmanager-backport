import asyncio
from viam.module.module import Module

try:
    from models.installer import Installer
except ModuleNotFoundError:
    # when running as local module with run.sh
    from .models.installer import Installer


if __name__ == '__main__':
    asyncio.run(Module.run_from_registry())