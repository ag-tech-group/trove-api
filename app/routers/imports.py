import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.image_utils import MAX_FILE_SIZE
from app.imports.catalogit import ImportFileError, plan_import, read_entries, read_media_index
from app.imports.commit import (
    already_imported_ids,
    attach_photo,
    commit_import,
    finish_import,
    photo_progress,
    undo_import,
)
from app.imports.plan import ImportPlan
from app.models import Image, User
from app.models.data_import import Import
from app.schemas.data_import import (
    ImportCommit,
    ImportPhotoRead,
    ImportRead,
    ImportSource,
    ImportStatus,
    ImportSummary,
)
from app.schemas.image import ImageRead
from app.storage import delete_files

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

    earlier = await already_imported_ids(session, str(user.id), source.value)
    record = Import(
        user_id=str(user.id),
        source=source.value,
        status=ImportStatus.PREVIEW.value,
        entries_filename=entries.filename or "entries",
        media_index_filename=media_index.filename if media_index else None,
        source_data={"entries": parsed_entries, "media": parsed_media},
        report={
            **plan.report(),
            "already_imported": sum(item.external_id in earlier for item in plan.items),
        },
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return await _import_read(session, record)


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
    """Get an import, its preview, and how far its photos have got."""
    return await _import_read(session, await _get_user_import(import_id, user, session))


@router.post("/{import_id}/commit", response_model=ImportRead)
async def commit(
    import_id: UUID,
    options: ImportCommit,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Create the items the preview lists, then wait for their photos.

    Items are grouped into collections, and tagged, by `groups`, keyed by the grouping
    keys the preview reported. The response's `pending_photos` names the files to
    upload to `POST /imports/{id}/photos`.
    """
    record = await _get_user_import(import_id, user, session)
    await commit_import(session, record, options)
    await session.refresh(record)
    return await _import_read(session, record)


@router.post("/{import_id}/photos", response_model=ImportPhotoRead)
async def upload_photo(
    import_id: UUID,
    file: UploadFile = File(
        ..., description="One photo from the export, sent under its own file name."
    ),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Upload one of the photos the import is waiting for; it is matched by file name.

    Uploading a photo that is already in place changes nothing. A photo that fails to
    process is marked failed and can be sent again.
    """
    record = await _get_user_import(import_id, user, session)
    data = await _read(file, MAX_FILE_SIZE, "photo")
    photo = await attach_photo(session, record, file.filename, data, str(user.id))
    image = await session.get(Image, photo.image_id) if photo.image_id else None
    return ImportPhotoRead(
        filename=photo.filename,
        status=photo.status,
        error=photo.error,
        image=ImageRead.model_validate(image) if image else None,
    )


@router.post("/{import_id}/finish", response_model=ImportRead)
async def finish(
    import_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Stop waiting for photos: those not uploaded, or that failed, are skipped."""
    record = await _get_user_import(import_id, user, session)
    await finish_import(session, record)
    await session.refresh(record)
    return await _import_read(session, record)


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import(
    import_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Undo an import: discard its preview, or delete everything it created.

    Items it created are deleted even if edited since. Collections and tags it created
    are deleted only if nothing else uses them.
    """
    record = await _get_user_import(import_id, user, session)
    storage_keys = await undo_import(session, record)
    await session.commit()
    # Best-effort object storage cleanup
    await delete_files(storage_keys)


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


async def _import_read(session: AsyncSession, record: Import) -> ImportRead:
    read = ImportRead.model_validate(record)
    if record.status != ImportStatus.PREVIEW:
        read.photos, read.pending_photos, read.failed_photos = await photo_progress(session, record)
    return read


async def _get_user_import(import_id: UUID, user: User, session: AsyncSession) -> Import:
    result = await session.execute(
        select(Import).where(Import.id == str(import_id), Import.user_id == str(user.id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")
    return record
