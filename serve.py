"""Production service entry point driven entirely by application settings."""
from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> int:
    """Run the production HTTP service on its configured host and port."""
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
