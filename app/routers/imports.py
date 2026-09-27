import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.imports.catalogit import ImportFileError, plan_import, read_entries, read_media_index
from app.imports.plan import ImportPlan
from app.models import User
from app.models.data_import import Import
from app.schemas.data_import import ImportRead, ImportSource, ImportStatus, ImportSummary

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_ENTRIES_UPLOAD = 20 * 1024 * 1024  # 20 MB
MAX_MEDIA_INDEX_UPLOAD = 10 * 1024 * 1024  # 10 MB


@router.post("", response_model=ImportRead, status_code=status.HTTP_201_CREATED)
async def create_import(
    entries: UploadFile = File(
        ..., description="The catalog's entries export: CatalogIt's zip as downloaded, or its JSON."
    ),
    media_index: UploadFile | None = File(
        default=None,
        description="CatalogIt's media index CSV, which says which photo belongs to which entry.",
    ),
    source: ImportSource = Form(default=ImportSource.CATALOGIT),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Read an export and preview what importing it would create. Nothing else is written."""
    entries_data = await _read(entries, MAX_ENTRIES_UPLOAD, "entries export")
    media_data = (
        await _read(media_index, MAX_MEDIA_INDEX_UPLOAD, "media index") if media_index else b""
    )

    try:
        # Parsing and planning thousands of entries is CPU work; off the event loop.
        parsed_entries, parsed_media, plan = await asyncio.to_thread(
            _plan, entries_data, media_data
        )
    except ImportFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record = Import(
        user_id=str(user.id),
        source=source.value,
        status=ImportStatus.PREVIEW.value,
        entries_filename=entries.filename or "entries",
        media_index_filename=media_index.filename if media_index else None,
        source_data={"entries": parsed_entries, "media": parsed_media},
        report=plan.report(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.get("", response_model=list[ImportSummary])
async def list_imports(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List the current user's imports, newest first."""
    result = await session.execute(
        select(Import).where(Import.user_id == str(user.id)).order_by(Import.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{import_id}", response_model=ImportRead)
async def get_import(
    import_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get an import and its preview."""
    return await _get_user_import(import_id, user, session)


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import(
    import_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Discard an import's preview."""
    record = await _get_user_import(import_id, user, session)
    await session.delete(record)
    await session.commit()


def _plan(entries_data: bytes, media_data: bytes) -> tuple[list[dict], list[dict], ImportPlan]:
    entries = read_entries(entries_data)
    media = read_media_index(media_data) if media_data else []
    return entries, media, plan_import(entries, media)


async def _read(file: UploadFile, limit: int, what: str) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The {what} is too large. Maximum size is {limit // (1024 * 1024)} MB",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"The {what} is empty")
    return data


async def _get_user_import(import_id: UUID, user: User, session: AsyncSession) -> Import:
    result = await session.execute(
        select(Import).where(Import.id == str(import_id), Import.user_id == str(user.id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")
    return record
