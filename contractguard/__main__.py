"""
contractguard.__main__
======================
Allows the package to be executed as ``python -m contractguard``.

This module simply delegates to the Click application defined in ``cli.py``
so that both invocation styles work:

    python -m contractguard audit <path>
    contractguard audit <path>          # via console_scripts entry point
"""

from contractguard.cli import cli

if __name__ == "__main__":
    cli()
