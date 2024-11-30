"""Process submodule providing functionality related to processes and their execution."""

from plugboard.process.local_process import LocalProcess
from plugboard.process.process import Process
from plugboard.process.process_builder import ProcessBuilder


__all__ = [
    "LocalProcess",
    "Process",
    "ProcessBuilder",
]
