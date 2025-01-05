"""Process submodule providing functionality related to processes and their execution."""

from plugboard.process.local_process import LocalProcess
from plugboard.process.process import Process
from plugboard.process.process_builder import ProcessBuilder
from plugboard.process.ray_process import RayProcess


__all__ = [
    "LocalProcess",
    "Process",
    "ProcessBuilder",
    "RayProcess",
]
