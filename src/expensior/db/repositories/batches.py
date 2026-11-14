"""Reading and writing import batches (layer 0 of ADR 0007). Never commits."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from expensior.db import models
from expensior.domain.records import ImportBatch
from expensior.domain.types import ImportStatus


def _record(row: models.ImportBatch) -> ImportBatch:
    return ImportBatch(
        id=row.id,
        account_id=row.account_id,
        source=row.source,
        format_version=row.format_version,
        file_name=row.file_name,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        status=ImportStatus(row.status),
        error=row.error,
        row_count=row.row_count,
        imported_at=row.imported_at,
    )


class BatchRepository:
    """Import batches of one session; the caller owns the transaction and the commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        account_id: int,
        source: str,
        sha256: str,
        source_bytes: bytes,
        file_name: str | None = None,
    ) -> ImportBatch:
        """Store the original bytes as a new batch with status ``received``, before any parsing."""
        row = models.ImportBatch(
            account_id=account_id,
            source=source,
            file_name=file_name,
            sha256=sha256,
            size_bytes=len(source_bytes),
            source_bytes=source_bytes,
            status=ImportStatus.RECEIVED.value,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, batch_id: int) -> ImportBatch | None:
        row = self._session.get(models.ImportBatch, batch_id)
        return _record(row) if row else None

    def find_by_sha256(self, sha256: str) -> list[ImportBatch]:
        """Batches with the same content, oldest first: the same file may be imported again."""
        rows = self._session.scalars(
            select(models.ImportBatch)
            .where(models.ImportBatch.sha256 == sha256)
            .order_by(models.ImportBatch.id)
        )
        return [_record(row) for row in rows]

    def source_bytes(self, batch_id: int) -> bytes | None:
        """The original bytes of a batch; loaded on their own because they can be megabytes."""
        return self._session.scalar(
            select(models.ImportBatch.source_bytes).where(models.ImportBatch.id == batch_id)
        )

    def update_status(
        self,
        batch_id: int,
        status: ImportStatus,
        *,
        error: str | None = None,
        format_version: str | None = None,
        header: list[str] | None = None,
        row_count: int | None = None,
    ) -> None:
        """Set the status; the other values are set only when given."""
        row = self._session.get(models.ImportBatch, batch_id)
        if row is None:
            raise LookupError(f"no import batch with id {batch_id}")
        row.status = status.value
        if error is not None:
            row.error = error
        if format_version is not None:
            row.format_version = format_version
        if header is not None:
            row.header = header
        if row_count is not None:
            row.row_count = row_count
        self._session.flush()
