"""Manual statement import: preview a CSV/Excel upload, then commit it.

Preview and commit both take the file, so nothing is staged server-side between
the two calls — fingerprints are deterministic, so the preview's counts hold.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.imports import parsers, reconcile
from app.imports.categorize import TRANSFERS, resolve_category
from app.imports.parsers import PRESETS, ParseError
from app.models import SOURCE_CSV, Account, ImportBatch, Transaction
from app.schemas import (
    AccountCoverageOut,
    AccountOut,
    DateRangeOut,
    ImportBatchOut,
    ImportCommitOut,
    ImportPresetOut,
    ImportPreviewOut,
    ImportRowOut,
    ManualAccountCreate,
    ManualAccountUpdate,
)

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SAMPLE_ROWS = 15


@router.get("/presets", response_model=list[ImportPresetOut])
def list_presets():
    return [ImportPresetOut(key=key, label=cmap.label) for key, cmap in PRESETS.items()]


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_manual_account(payload: ManualAccountCreate, db: Session = Depends(get_db)):
    """An account with no Plaid identity, to import statements into."""
    account = Account(
        source=SOURCE_CSV,
        name=payload.name,
        type=payload.type,
        subtype=payload.subtype,
        currency=payload.currency,
        current_balance=payload.current_balance,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_manual_account(
    account_id: int, payload: ManualAccountUpdate, db: Session = Depends(get_db)
):
    """Correct a manual account — most often its `type`, since that decides
    whether net worth treats the balance as an asset or a debt. Plaid-linked
    accounts are not editable here: their next sync would overwrite it anyway."""
    account = db.query(Account).filter_by(id=account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.source != SOURCE_CSV:
        raise HTTPException(
            status_code=400, detail="Only manually-created accounts can be edited"
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


def _load(file: UploadFile, preset: str, account_id: int, db: Session):
    account = db.query(Account).filter_by(id=account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    cmap = PRESETS.get(preset)
    if cmap is None:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset}")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File larger than 10MB")
    try:
        rows = parsers.parse(data, file.filename or "upload.csv", cmap)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return account, rows


def _range(value) -> DateRangeOut:
    return DateRangeOut(start=value.start, end=value.end)


def _row_out(classified, category: str) -> ImportRowOut:
    return ImportRowOut(
        date=classified.row.date,
        description=classified.row.description,
        amount=classified.row.amount,
        currency=classified.row.currency,
        status=classified.status,
        existing_amount=classified.existing_amount,
        category=category,
    )


@router.post("/preview", response_model=ImportPreviewOut)
def preview_import(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    preset: str = Form("rbc"),
    db: Session = Depends(get_db),
):
    """Parse and classify without writing. Reports overlap, conflicts and gaps."""
    account, rows = _load(file, preset, account_id, db)
    result = reconcile.reconcile(db, account.id, rows)
    # Pair each classified row with the category it would be written with, so the
    # preview shows transfer detection before anything is committed.
    categorized = [(c, resolve_category(db, c.row.description)) for c in result.rows]

    return ImportPreviewOut(
        account_id=account.id,
        filename=file.filename or "upload.csv",
        preset=preset,
        period=_range(result.period),
        parsed=len(result.rows),
        new=result.count(reconcile.NEW),
        duplicate=result.count(reconcile.DUPLICATE),
        conflict=result.count(reconcile.CONFLICT),
        transfers=sum(
            1
            for c, category in categorized
            if c.status != reconcile.DUPLICATE and category == TRANSFERS
        ),
        gaps_before=[_range(g) for g in result.gaps_before],
        gaps_after=[_range(g) for g in result.gaps_after],
        conflicts=[
            _row_out(c, category)
            for c, category in categorized
            if c.status == reconcile.CONFLICT
        ],
        sample=[_row_out(c, category) for c, category in categorized[:SAMPLE_ROWS]],
    )


@router.post("/commit", response_model=ImportCommitOut)
def commit_import(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    preset: str = Form("rbc"),
    include_conflicts: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Write the new rows. Duplicates are always skipped; conflicting rows are
    skipped unless `include_conflicts`, so a restated amount is a deliberate choice."""
    account, rows = _load(file, preset, account_id, db)
    result = reconcile.reconcile(db, account.id, rows)

    batch = ImportBatch(
        account_id=account.id,
        filename=file.filename or "upload.csv",
        preset=preset,
        period_start=result.period.start,
        period_end=result.period.end,
        rows_parsed=len(result.rows),
        rows_duplicate=result.count(reconcile.DUPLICATE),
        rows_conflicting=result.count(reconcile.CONFLICT),
    )
    db.add(batch)
    db.flush()

    to_write = result.new_rows + (result.conflicting_rows if include_conflicts else [])
    for classified in to_write:
        row = classified.row
        db.add(
            Transaction(
                account_id=account.id,
                import_fingerprint=classified.fingerprint,
                import_batch_id=batch.id,
                source=SOURCE_CSV,
                date=row.date,
                name=row.description,
                amount=row.amount,
                currency=row.currency or account.currency,
                category=resolve_category(db, row.description),
            )
        )
    batch.rows_imported = len(to_write)
    db.commit()

    return ImportCommitOut(
        batch_id=batch.id,
        imported=batch.rows_imported,
        duplicate=batch.rows_duplicate,
        conflict=batch.rows_conflicting,
        period=_range(result.period),
        gaps=[_range(g) for g in reconcile.find_gaps(reconcile.covered_ranges(db, account.id))],
    )


@router.get("/batches", response_model=list[ImportBatchOut])
def list_batches(db: Session = Depends(get_db)):
    return db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()


@router.get("/coverage", response_model=list[AccountCoverageOut])
def coverage(db: Session = Depends(get_db)):
    """Per-account data coverage and the gaps in it — the monitoring surface."""
    out = []
    for account in db.query(Account).all():
        covered = reconcile.covered_ranges(db, account.id)
        batches = (
            db.query(ImportBatch)
            .filter(ImportBatch.account_id == account.id)
            .order_by(ImportBatch.period_end.desc())
            .first()
        )
        out.append(
            AccountCoverageOut(
                account_id=account.id,
                account_name=account.name,
                account_type=account.type,
                source=account.source,
                covered=[_range(r) for r in covered],
                gaps=[_range(g) for g in reconcile.find_gaps(covered)],
                last_imported_period_end=batches.period_end if batches else None,
            )
        )
    return out
