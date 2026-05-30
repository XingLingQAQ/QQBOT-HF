"""System status endpoint."""

from fastapi import APIRouter, Depends

from .. import auth, config, process_manager

router = APIRouter(tags=["system"], dependencies=[Depends(auth.require_auth)])


@router.get("/status")
def status():
    return {
        "lagrange": process_manager.get_status(config.PROG_LAGRANGE),
        "nonebot": process_manager.get_status(config.PROG_NONEBOT),
        "backend": process_manager.get_status(config.PROG_BACKEND),
    }
