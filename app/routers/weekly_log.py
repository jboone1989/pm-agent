from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.schemas import (
    OperationLogRead,
    WeeklyLogResponse,
    WeeklyReportGenerateResponse,
    WeeklyReportRead,
)
from app.services import operation_log as op_log
from app.services import weekly_report as weekly_report_service

router = APIRouter(prefix="/api/weekly-log", tags=["weekly-log"])


@router.get("", response_model=WeeklyLogResponse)
def get_weekly_log(week: Optional[str] = None, session: Session = Depends(get_session)):
    week_key = week or op_log.week_key_from_dt()
    start, end = op_log.parse_week_key(week_key)
    entries = op_log.list_operations(session, week_key)
    saved = weekly_report_service.get_saved_report(session, week_key)
    report = (
        WeeklyReportRead(
            week_key=saved.week_key,
            this_week_summary=saved.this_week_summary,
            next_week_plan=saved.next_week_plan,
            generated_at=saved.generated_at,
        )
        if saved
        else None
    )
    return WeeklyLogResponse(
        week_key=week_key,
        week_label=op_log.week_label(week_key),
        start_date=start,
        end_date=end,
        entries=[OperationLogRead.model_validate(entry, from_attributes=True) for entry in entries],
        report=report,
    )


@router.post("/generate", response_model=WeeklyReportGenerateResponse)
def generate_weekly_report(week: Optional[str] = None, session: Session = Depends(get_session)):
    week_key = week or op_log.week_key_from_dt()
    report = weekly_report_service.generate_report(session, week_key)
    return WeeklyReportGenerateResponse(
        week_key=report.week_key,
        this_week_summary=report.this_week_summary,
        next_week_plan=report.next_week_plan,
        generated_at=report.generated_at,
    )
