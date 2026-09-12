"""Folder API endpoints for organizing uploads (one level, flat).

All routes require a logged-in user and operate on that account's folders
only (``owner_id`` is always the current user).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.database import (
    create_folder,
    delete_folder,
    folder_invoice_counts,
    get_folder,
    list_folders,
    rename_folder,
)

router = APIRouter(prefix="/api")


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("/folders")
async def get_folders(user=Depends(get_current_user)):
    """List this account's folders with an invoice count for each."""
    folders = list_folders(user["id"])
    counts = folder_invoice_counts(user["id"])
    return [
        {
            "id": folder["id"],
            "name": folder["name"],
            "invoice_count": counts.get(folder["id"], 0),
            "created_at": folder["created_at"],
        }
        for folder in folders
    ]


@router.post("/folders", status_code=201)
async def add_folder(payload: FolderCreate, user=Depends(get_current_user)):
    """Create a folder in this account."""
    name = payload.name.strip()
    folder = create_folder(user["id"], name)
    return {"id": folder["id"], "name": folder["name"]}


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: str, payload: FolderCreate, user=Depends(get_current_user)):
    """Rename a folder owned by this account."""
    if not get_folder(folder_id, user["id"]):
        raise HTTPException(status_code=404, detail="Folder not found")
    updated = rename_folder(folder_id, user["id"], payload.name.strip())
    if not updated:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"id": updated["id"], "name": updated["name"]}


@router.delete("/folders/{folder_id}", status_code=204)
async def remove_folder(folder_id: str, user=Depends(get_current_user)):
    """Delete a folder. Its invoices survive under 'No folder' (DB-level)."""
    if not delete_folder(folder_id, user["id"]):
        raise HTTPException(status_code=404, detail="Folder not found")
    return None
