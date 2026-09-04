from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import trails

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trails.router)


@app.get("/")
def root():
    return {
        "message": "Trail Q API running"
    }