import asyncio
from viam.module.module import Module

try:
    from models.installer import Installer
except ModuleNotFoundError:
    # when running as local module with run.sh
    from .models.installer import Installer


async def main():
    """Main function to run the NetworkManager backport module."""
    module = Module.from_args()
    module.add_model_from_registry(Installer.MODEL, Installer)
    await module.start()


if __name__ == '__main__':
    asyncio.run(main())