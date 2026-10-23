"""PyInstaller entry point (keeps package-relative imports intact)."""
from tool.runtime_patcher import main

if __name__ == '__main__':
    raise SystemExit(main())
