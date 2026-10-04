from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .audit import router as audit_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .edit import router as edit_router
from .ips import router as ips_router
from .users import router as users_router
from .vlans import router as vlans_router

app = FastAPI(title="IP Inventory Management")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(vlans_router)
app.include_router(ips_router)
app.include_router(audit_router)
app.include_router(edit_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- Serve the built React app (frontend/dist) from the same server and port ----
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if (DIST / "index.html").is_file():
    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")