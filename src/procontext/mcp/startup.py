"""Legacy entrypoint — delegates to procontext.cli.main.

Kept for backward compatibility with ``python -m procontext.mcp.startup``
and any existing references to this module path.
"""

from procontext.cli.main import main

if __name__ == "__main__":
    main()
