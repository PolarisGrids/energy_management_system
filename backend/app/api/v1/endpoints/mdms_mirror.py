from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.mdms import (
    VEEDailySummary, VEEException, ConsumerAccount,
    TariffSchedule, NTLSuspect, PowerQualityZone,
)

router = APIRouter()


@router.get("/vee/summary")
def vee_summary(days: int = Query(7, le=30), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(VEEDailySummary).order_by(VEEDailySummary.date).limit(days).all()
    return {"days": [r.date.strftime("%d %b") for r in rows],
            "validated": [r.validated_count for r in rows],
            "estimated": [r.estimated_count for r in rows],
            "failed": [r.failed_count for r in rows]}


@router.get("/vee/exceptions")
def vee_exceptions(status: Optional[str] = None, limit: int = Query(20, le=100), offset: int = 0,
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(VEEException)
    if status:
        q = q.filter(VEEException.status == status)
    exceptions = q.order_by(desc(VEEException.date)).offset(offset).limit(limit).all()
    return {"exceptions": [{"serial": e.meter_serial, "type": e.exception_type,
                             "date": e.date.strftime("%d %b"), "orig": e.original_value,
                             "corr": e.corrected_value, "status": e.status}
                            for e in exceptions]}


@router.get("/consumers")
def list_consumers(search: Optional[str] = None, limit: int = Query(20, le=100), offset: int = 0,
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(ConsumerAccount)
    if search:
        q = q.filter(ConsumerAccount.customer_name.ilike(f"%{search}%") | ConsumerAccount.meter_serial.ilike(f"%{search}%"))
    consumers = q.offset(offset).limit(limit).all()
    return {"consumers": [{"acct": c.account_number, "name": c.customer_name, "addr": c.address,
                            "tariff": c.tariff_name, "serial": c.meter_serial,
                            "transformer": c.transformer_id, "phase": c.phase,
                            "balance": c.prepaid_balance} for c in consumers]}


@router.get("/tariffs")
def list_tariffs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    tariffs = db.query(TariffSchedule).all()
    return {"tariffs": [{"name": t.name, "type": t.tariff_type,
                          "offpeak": f"R {t.offpeak_rate:.2f}", "std": f"R {t.standard_rate:.2f}",
                          "peak": f"R {t.peak_rate:.2f}", "from": t.effective_from.strftime("%Y-%m-%d")}
                         for t in tariffs]}


@router.get("/ntl")
def list_ntl(flag: Optional[str] = None, limit: int = Query(20, le=100),
             db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(NTLSuspect)
    if flag:
        q = q.filter(NTLSuspect.flag == flag)
    suspects = q.order_by(desc(NTLSuspect.risk_score)).limit(limit).all()
    return {"suspects": [{"serial": s.meter_serial, "customer": s.customer_name,
                           "pattern": s.pattern_description, "score": s.risk_score,
                           "flag": s.flag} for s in suspects]}


@router.get("/power-quality")
def power_quality(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    zones = db.query(PowerQualityZone).all()
    return {"zones": [{"zone": z.zone_name, "vDev": z.voltage_deviation_pct,
                        "thd": z.thd_pct, "flicker": z.flicker_pst, "ok": z.compliant}
                       for z in zones]}
