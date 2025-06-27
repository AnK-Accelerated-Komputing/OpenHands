import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import threading

from openhands.core.logger import openhands_logger as logger
from openhands.events.action import Action
from openhands.events.observation import Observation
from openhands.runtime.plugins.requirement import Plugin, PluginRequirement
from openhands.runtime.utils.system import check_port_available
from openhands.utils.shutdown_listener import should_continue


@dataclass
class CascadeRequirement(PluginRequirement):
    name: str = 'cascade'

class CascadePlugin(Plugin):
    name: str = 'cascade'
    cascade_port: Optional[int] = None
    gateway_process: Optional[asyncio.subprocess.Process] = None
    server_thread: Optional[threading.Thread] = None

    async def initialize(self, username: str) -> None:
        self._setup_cascade_settings()

        try:
            self.cascade_port = int(os.environ['CASCADE_PORT'])
        except (KeyError, ValueError):
            logger.warning('CASCADE_PORT environment variable not set or invalid.')
            return

        if not check_port_available(self.cascade_port):
            logger.warning(f'Port {self.cascade_port} is not available.')
            return

        cascade_directory = '/openhands/.cascade-studio'

        # Ensure directory exists and has proper permissions
        if not os.path.exists(cascade_directory):
            logger.error(f'CascadeStudio directory not found: {cascade_directory}')
            return

        # Verify required files exist
        required_files = [
            'index.html'
        ]

        for file_path in required_files:
            full_path = os.path.join(cascade_directory, file_path)
            if not os.path.exists(full_path):
                logger.warning(f'Required file not found: {full_path}')

        await self._start_subprocess_server(cascade_directory, username)

    async def _start_subprocess_server(self, cascade_directory: str, username: str) -> None:
        """Fallback to subprocess method with enhanced server options"""
        # Try different server commands in order of preference
        server_command = rf"""
            mkdir -p /run            # ensure PID dir exists
            chown -R {username}:{username} {cascade_directory}
            chmod -R 755 {cascade_directory}
            cd {cascade_directory}/serve

            ./change_port.sh {self.cascade_port}
            echo $?
            echo "nginx running"
            exec nginx -g 'daemon off; error_log /dev/stdout info;'
            """

        try:
            logger.info(f'Trying nginx http server method')
            self.gateway_process = await asyncio.create_subprocess_shell(
                server_command,
                stderr=asyncio.subprocess.STDOUT,
                stdout=asyncio.subprocess.PIPE,
            )

            output = ''
            startup_keywords = ['start worker processes','nginx']
            timeout_count = 0
            max_timeout = 30  # 30 seconds timeout

            while should_continue() and self.gateway_process.stdout is not None and timeout_count < max_timeout:
                try:
                    line_bytes = await asyncio.wait_for(
                        self.gateway_process.stdout.readline(),
                        timeout=1.0
                    )

                    if not line_bytes:
                        break

                    line = line_bytes.decode('utf-8').strip()
                    if line:
                        logger.debug(f'Server output: {line}')
                        output += line + '\n'

                        # Check if server started successfully
                        if any(keyword in line for keyword in startup_keywords):
                            logger.info(f'CascadeStudio server started successfully at port {self.cascade_port}')
                            return

                except asyncio.TimeoutError:
                    timeout_count += 1
                    if timeout_count % 5 == 0:  # Log every 5 seconds
                        logger.debug('Waiting for CascadeStudio server to start...')
                    continue

            # If we get here, the server didn't start properly with this method
            logger.warning(f'Server timed out or failed')
            if self.gateway_process:
                self.gateway_process.terminate()
                await self.gateway_process.wait()

        except Exception as e:
            logger.warning(f'Server startup failed: {e}')

        raise RuntimeError('All server startup methods failed')

    def _setup_cascade_settings(self) -> None:
        """Setup the Cascade Editor settings"""
        # Get the path to the settings.json file in the plugin directory
        current_dir = Path(__file__).parent
        cascade_dir = Path('/openhands/.cascade-studio')

        # Ensure the cascade directory exists
        cascade_dir.mkdir(parents=True, exist_ok=True)

        # You can add additional setup logic here if needed
        logger.debug(f'CascadeStudio settings initialized. Directory: {cascade_dir}')

    async def cleanup(self) -> None:
        """Clean up resources when shutting down"""
        if self.server_thread and self.server_thread.is_alive():
            try:
                self.server_thread.join(timeout=5)
            except Exception as e:
                logger.warning(f'Error joining server thread: {e}')

        if self.gateway_process:
            try:
                self.gateway_process.terminate()
                await asyncio.wait_for(self.gateway_process.wait(), timeout=5)
                logger.info('Subprocess server stopped')
            except Exception as e:
                logger.warning(f'Error stopping subprocess server: {e}')

    async def run(self, action: Action) -> Observation:
        """Run the plugin for a given action."""
        raise NotImplementedError('CASCADE does not support run method')
