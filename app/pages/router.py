from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pathlib import Path

router = APIRouter(prefix="", tags=["Frontend"])
dist_index = Path("app/static/dist/index.html")


def serve_built_frontend() -> Response:
    if dist_index.exists():
        return FileResponse(dist_index, media_type="text/html")
    return Response("Frontend bundle is not built", status_code=503, media_type="text/plain")


@router.get("/")
async def home():
    return serve_built_frontend()


@router.get("/giveaways/{giveaway_id}")
async def giveaway_page(giveaway_id: int):
    return serve_built_frontend()
