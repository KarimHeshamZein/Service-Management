"""Development entry point: python run.py"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    # 0.0.0.0 is a bind address, not something a browser can open.
    print("\n  Service Management System")
    print(f"  Open http://localhost:{settings.app_port} in your browser")
    print(
        "  On a phone, use this machine's LAN address, e.g. "
        f"http://192.168.1.x:{settings.app_port}\n"
    )
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )
