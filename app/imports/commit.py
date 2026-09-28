"""Committing an import, attaching its photos as they arrive, and undoing it."""

import asyncio
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.images import add_image, owned_storage_keys
from app.imports.catalogit import plan_import
from app.imports.plan import PlannedPhoto
from app.imports.values import clip
from app.models import Collection, Item, ItemNote, Mark, Tag, Valuation, item_tags
from app.models.data_import import Import, ImportEntry, ImportPhoto
from app.schemas.data_import import (
    CollectionTarget,
    ImportCommit,
    ImportOutcome,
    ImportPhotoFailure,
    ImportPhotoProgress,
    ImportPhotoStatus,
    ImportStatus,
)
from app.storage import delete_file


async def already_imported_ids(
    session: AsyncSession, user_id: str, source: str, exclude: str | None = None
) -> set[str]:
    """Source IDs an import of this catalog already brought in, whose items still exist."""
    stmt = (
        select(ImportEntry.external_id)
        .join(Import, ImportEntry.import_id == Import.id)
        .join(Item, ImportEntry.item_id == Item.id)
        .where(Import.user_id == user_id, Import.source == source)
    )
    if exclude is not None:
        stmt = stmt.where(Import.id != exclude)
    return set((await session.execute(stmt)).scalars().all())


async def commit_import(session: AsyncSession, record: Import, options: ImportCommit) -> None:
    """Create everything the import's plan lists, and expect its photos."""
    if record.status != ImportStatus.PREVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT, "This import has already been committed")

    await session.refresh(record, ["source_data"])
    source = record.source_data
    plan = await asyncio.to_thread(plan_import, source["entries"], source["media"])
    skip = (
        await already_imported_ids(session, record.user_id, record.source, exclude=record.id)
        if options.skip_already_imported
        else set()
    )
    collections = _Collections(session, record.user_id)
    await collections.check(options)
    tags = await _Tags.load(session, record.user_id)
    groups = {key.casefold(): target for key, target in options.groups.items()}
    as_marks = {name.casefold() for name in options.mark_photos}

    items: list[Item] = []
    rows: list[ImportEntry | ImportPhoto] = []
    # Built whole before being added, so the lookups below must not flush them early.
    with session.no_autoflush:
        for planned in plan.items:
            if planned.external_id in skip:
                continue
            key = planned.groups.get(options.grouping) if options.grouping else None
            target = groups.get(key.casefold(), options.default) if key else options.default

            item = Item(id=str(uuid4()), user_id=record.user_id, **planned.fields)
            item.collection = await collections.resolve(target.collection)
            item.tags = tags.get(planned.tags + target.tags)
            item.item_notes = [ItemNote(title=note.title, body=note.body) for note in planned.notes]
            item.marks = [
                Mark(title=mark.title, description=mark.description) for mark in planned.marks
            ]
            item.valuations = [Valuation(**vars(valuation)) for valuation in planned.valuations]
            items.append(item)
            rows.append(
                ImportEntry(import_id=record.id, external_id=planned.external_id, item_id=item.id)
            )

            position = 0
            for photo in planned.photos:
                mark = None
                if photo.filename.casefold() in as_marks:
                    mark = Mark(id=str(uuid4()), title=_mark_title(photo))
                    item.marks.append(mark)
                rows.append(
                    ImportPhoto(
                        import_id=record.id,
                        item_id=None if mark else item.id,
                        mark_id=mark.id if mark else None,
                        filename=photo.filename,
                        caption=photo.caption,
                        description=photo.description,
                        position=0 if mark else position,
                        status=ImportPhotoStatus.PENDING.value,
                    )
                )
                position += 0 if mark else 1

    # Items first, flushed. The entry and photo rows refer to items and marks by id
    # alone, with no relationship from which the flush could order the inserts, and
    # Postgres checks those foreign keys row by row.
    session.add_all(items)
    await session.flush()
    session.add_all(rows)
    photos = sum(isinstance(row, ImportPhoto) for row in rows)

    now = datetime.now(UTC)
    record.status = ImportStatus.IMPORTING.value
    record.committed_at = now
    record.options = options.model_dump(mode="json")
    record.outcome = ImportOutcome(
        items=len(items), skipped=len(plan.items) - len(items), photos=photos
    ).model_dump()
    record.created_collection_ids = [collection.id for collection in collections.created]
    record.created_tag_ids = [tag.id for tag in tags.created]
    if not photos:
        _complete(record, now)
    await session.commit()


async def attach_photo(
    session: AsyncSession, record: Import, upload_name: str | None, data: bytes, user_id: str
) -> ImportPhoto:
    """Store an uploaded file as the photo the import expects by that name."""
    if record.status != ImportStatus.IMPORTING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This import isn't waiting for photos")
    # Browsers may send the path inside the zip; the index names the file alone.
    name = re.split(r"[\\/]", upload_name or "")[-1]
    photo = await session.scalar(
        select(ImportPhoto).where(
            ImportPhoto.import_id == record.id, func.lower(ImportPhoto.filename) == name.lower()
        )
    )
    if photo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"This import isn't expecting a photo called {name!r}"
        )
    if photo.status == ImportPhotoStatus.DONE:
        return photo

    item = await session.get(Item, photo.item_id) if photo.item_id else None
    mark = await session.get(Mark, photo.mark_id) if photo.mark_id else None
    if item is None and mark is None:
        photo.status = ImportPhotoStatus.SKIPPED.value
        photo.error = "What it belonged to was deleted after the import was committed"
        await _complete_if_done(session, record)
        await session.commit()
        return photo

    try:
        image = await add_image(
            session,
            data,
            user_id=user_id,
            item=item,
            mark=mark,
            filename=photo.filename,
            caption=photo.caption,
            description=photo.description,
            position=photo.position if item is not None else None,
        )
    except HTTPException as exc:
        photo.status = ImportPhotoStatus.FAILED.value
        photo.error = clip(str(exc.detail), 500)[0]
        await session.commit()
        raise
    await session.flush()

    # A conditional update, not a read then a write: of two uploads of one file
    # racing each other, only the first to commit claims the row.
    claimed = await session.execute(
        update(ImportPhoto)
        .where(ImportPhoto.id == photo.id, ImportPhoto.status != ImportPhotoStatus.DONE.value)
        .values(status=ImportPhotoStatus.DONE.value, image_id=image.id, error=None)
    )
    if claimed.rowcount == 0:
        await session.rollback()
        await delete_file(image.storage_key)
        await session.refresh(photo)
        return photo

    await _complete_if_done(session, record)
    await session.commit()
    await session.refresh(photo)
    return photo


async def finish_import(session: AsyncSession, record: Import) -> None:
    """Stop waiting: photos not yet uploaded, or that failed, are skipped."""
    if record.status != ImportStatus.IMPORTING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This import isn't waiting for photos")
    await session.execute(
        update(ImportPhoto)
        .where(
            ImportPhoto.import_id == record.id,
            ImportPhoto.status.in_(
                [ImportPhotoStatus.PENDING.value, ImportPhotoStatus.FAILED.value]
            ),
        )
        .values(status=ImportPhotoStatus.SKIPPED.value)
    )
    _complete(record, datetime.now(UTC))
    await session.commit()


async def undo_import(session: AsyncSession, record: Import) -> list[str]:
    """Delete the import and everything it created; return the storage keys it owned.

    Items it created go even if edited since. Collections and tags it created go only
    once nothing else uses them. The caller deletes the returned keys after committing.
    """
    item_ids = (
        (
            await session.execute(
                select(ImportEntry.item_id).where(
                    ImportEntry.import_id == record.id, ImportEntry.item_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    items = (
        (
            await session.execute(
                select(Item).where(Item.id.in_(item_ids), Item.user_id == record.user_id)
            )
        )
        .scalars()
        .all()
    )
    keys = [key for item in items for key in owned_storage_keys(item)]

    await session.execute(delete(ImportPhoto).where(ImportPhoto.import_id == record.id))
    await session.execute(delete(ImportEntry).where(ImportEntry.import_id == record.id))
    for item in items:
        await session.delete(item)
    await session.flush()

    for collection_id in record.created_collection_ids or []:
        collection = await session.get(Collection, collection_id)
        if collection is not None and not await session.scalar(
            select(func.count()).select_from(Item).where(Item.collection_id == collection.id)
        ):
            await session.delete(collection)
    for tag_id in record.created_tag_ids or []:
        tag = await session.get(Tag, tag_id)
        if tag is not None and not await session.scalar(
            select(func.count()).select_from(item_tags).where(item_tags.c.tag_id == tag.id)
        ):
            await session.delete(tag)
    await session.delete(record)
    return keys


async def photo_progress(
    session: AsyncSession, record: Import
) -> tuple[ImportPhotoProgress, list[str], list[ImportPhotoFailure]]:
    rows = (
        await session.execute(
            select(ImportPhoto.filename, ImportPhoto.status, ImportPhoto.error)
            .where(ImportPhoto.import_id == record.id)
            .order_by(ImportPhoto.filename)
        )
    ).all()
    progress = ImportPhotoProgress(total=len(rows))
    for _, photo_status, _ in rows:
        setattr(progress, photo_status, getattr(progress, photo_status) + 1)
    pending = [name for name, photo_status, _ in rows if photo_status == ImportPhotoStatus.PENDING]
    failed = [
        ImportPhotoFailure(filename=name, error=error)
        for name, photo_status, error in rows
        if photo_status == ImportPhotoStatus.FAILED
    ]
    return progress, pending, failed


def _complete(record: Import, when: datetime) -> None:
    record.status = ImportStatus.COMPLETED.value
    record.completed_at = when
    # The export's contents, including CatalogIt's record of who typed each entry,
    # are only needed until the import is done.
    record.source_data = None


async def _complete_if_done(session: AsyncSession, record: Import) -> None:
    await session.flush()
    waiting = await session.scalar(
        select(func.count())
        .select_from(ImportPhoto)
        .where(
            ImportPhoto.import_id == record.id,
            ImportPhoto.status.in_(
                [ImportPhotoStatus.PENDING.value, ImportPhotoStatus.FAILED.value]
            ),
        )
    )
    if not waiting:
        _complete(record, datetime.now(UTC))


def _mark_title(photo: PlannedPhoto) -> str:
    text = photo.caption or next(iter((photo.description or "").splitlines()), "") or "Mark"
    return clip(text, 200)[0]


class _Collections:
    """Collections the commit's targets name: looked up, or created once by name."""

    def __init__(self, session: AsyncSession, user_id: str) -> None:
        self.session = session
        self.user_id = user_id
        self.by_id: dict[str, Collection] = {}
        self.by_name: dict[str, Collection] = {}
        self.created: list[Collection] = []

    async def check(self, options: ImportCommit) -> None:
        """Refuse a commit naming another account's collection before writing anything."""
        for target in [options.default, *options.groups.values()]:
            await self.resolve(target.collection, create=False)

    async def resolve(
        self, target: CollectionTarget | None, *, create: bool = True
    ) -> Collection | None:
        if target is None:
            return None
        if target.id is not None:
            key = str(target.id)
            if key not in self.by_id:
                collection = await self.session.scalar(
                    select(Collection).where(
                        Collection.id == key, Collection.user_id == self.user_id
                    )
                )
                if collection is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Collection {key} not found")
                self.by_id[key] = collection
            return self.by_id[key]
        name = target.name.casefold()
        if name not in self.by_name:
            existing = await self.session.scalar(
                select(Collection).where(
                    Collection.user_id == self.user_id, func.lower(Collection.name) == name
                )
            )
            if existing is None and not create:
                return None
            if existing is None:
                existing = Collection(id=str(uuid4()), user_id=self.user_id, name=target.name)
                self.session.add(existing)
                self.created.append(existing)
            self.by_name[name] = existing
        return self.by_name[name]


class _Tags:
    """The account's tags by name, ignoring case, creating those it lacks."""

    def __init__(self, session: AsyncSession, user_id: str, existing: dict[str, Tag]) -> None:
        self.session = session
        self.user_id = user_id
        self.existing = existing
        self.created: list[Tag] = []

    @classmethod
    async def load(cls, session: AsyncSession, user_id: str) -> _Tags:
        tags = (await session.execute(select(Tag).where(Tag.user_id == user_id))).scalars().all()
        return cls(session, user_id, {tag.name.casefold(): tag for tag in tags})

    def get(self, names: list[str]) -> list[Tag]:
        found: list[Tag] = []
        for name in names:
            key = name.casefold()
            if key not in self.existing:
                tag = Tag(id=str(uuid4()), user_id=self.user_id, name=name)
                self.session.add(tag)
                self.existing[key] = tag
                self.created.append(tag)
            if self.existing[key] not in found:
                found.append(self.existing[key])
        return found
