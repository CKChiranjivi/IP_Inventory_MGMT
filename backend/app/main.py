from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .audit import router as audit_router
from .auth import router as auth_router
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


@app.get("/api/health")
def health():
    return {"status": "ok"}