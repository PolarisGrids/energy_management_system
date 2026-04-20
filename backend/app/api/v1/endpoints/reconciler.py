"""Reconciler API — serves compliance audit, feature status, and reconciliation data.

Reads from the local reconciler SQLite database at ~/.reconciler/history.db.
This is a dev-environment diagnostic endpoint — no auth required.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

router = APIRouter()

RECONCILER_DB = str(Path.home() / ".reconciler" / "history.db")


def _get_conn() -> sqlite3.Connection:
    """Get SQLite connection to reconciler history DB."""
    db_path = Path(RECONCILER_DB)
    if not db_path.exists():
        raise HTTPException(status_code=503, detail="Reconciler database not found. Run 'reconciler setup' first.")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/summary")
def get_summary():
    """Get reconciler overview: latest of each run type + counts."""
    conn = _get_conn()
    try:
        # Latest reconciliation run
        recon = conn.execute(
            "SELECT * FROM reconciliation_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        # Latest compliance audits (one per standard)
        audits = conn.execute(
            "SELECT * FROM compliance_audits ORDER BY run_at DESC LIMIT 30"
        ).fetchall()

        # Latest feature status
        feature_report = conn.execute(
            "SELECT * FROM feature_status_reports ORDER BY run_at DESC LIMIT 1"
        ).fetchone()

        feature_items = []
        if feature_report:
            feature_items = conn.execute(
                "SELECT * FROM feature_status_items WHERE report_id = ? ORDER BY demo_item_score DESC",
                (feature_report["id"],)
            ).fetchall()

        return {
            "reconciliation": dict(recon) if recon else None,
            "compliance_audits": [dict(a) for a in audits],
            "feature_report": dict(feature_report) if feature_report else None,
            "feature_items": [dict(i) for i in feature_items],
        }
    finally:
        conn.close()


@router.get("/compliance")
def get_compliance(standard: Optional[str] = Query(None, description="Filter by standard name")):
    """Get compliance audit results with findings."""
    conn = _get_conn()
    try:
        if standard:
            audits = conn.execute(
                "SELECT * FROM compliance_audits WHERE LOWER(standard_name) LIKE ? ORDER BY run_at DESC",
                (f"%{standard.lower()}%",)
            ).fetchall()
        else:
            audits = conn.execute(
                "SELECT * FROM compliance_audits ORDER BY run_at DESC LIMIT 30"
            ).fetchall()

        results = []
        for audit in audits:
            findings = conn.execute(
                "SELECT * FROM compliance_findings WHERE audit_id = ? ORDER BY status",
                (audit["id"],)
            ).fetchall()
            results.append({
                "audit": dict(audit),
                "findings": [dict(f) for f in findings],
            })

        return {"audits": results, "total": len(results)}
    finally:
        conn.close()


@router.get("/compliance/matrix")
def get_compliance_matrix():
    """Get aggregated compliance matrix across all standards."""
    conn = _get_conn()
    try:
        audits = conn.execute(
            "SELECT * FROM compliance_audits ORDER BY run_at DESC LIMIT 30"
        ).fetchall()

        matrix = []
        for a in audits:
            matrix.append({
                "standard": a["standard_name"],
                "total": a["total_clauses"],
                "compliant": a["compliant_count"],
                "partial": a["partial_count"],
                "non_compliant": a["non_compliant_count"],
                "not_applicable": a["not_applicable_count"],
                "compliance_pct": a["compliance_pct"],
                "run_at": a["run_at"],
            })

        return {"matrix": matrix}
    finally:
        conn.close()


@router.get("/features")
def get_features():
    """Get latest feature completion status."""
    conn = _get_conn()
    try:
        report = conn.execute(
            "SELECT * FROM feature_status_reports ORDER BY run_at DESC LIMIT 1"
        ).fetchone()

        if not report:
            return {"report": None, "items": []}

        items = conn.execute(
            "SELECT * FROM feature_status_items WHERE report_id = ? ORDER BY demo_item_score DESC",
            (report["id"],)
        ).fetchall()

        return {
            "report": dict(report),
            "items": [dict(i) for i in items],
        }
    finally:
        conn.close()


@router.get("/reconciliation")
def get_reconciliation(limit: int = Query(10, le=50)):
    """Get reconciliation run history."""
    conn = _get_conn()
    try:
        runs = conn.execute(
            "SELECT * FROM reconciliation_runs ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()

        return {"runs": [dict(r) for r in runs]}
    finally:
        conn.close()


@router.get("/reconciliation/{run_id}/findings")
def get_reconciliation_findings(run_id: str, limit: int = Query(100, le=500)):
    """Get findings for a specific reconciliation run."""
    conn = _get_conn()
    try:
        findings = conn.execute(
            "SELECT * FROM reconciliation_findings WHERE run_id = ? LIMIT ?",
            (run_id, limit)
        ).fetchall()

        return {"findings": [dict(f) for f in findings], "total": len(findings)}
    finally:
        conn.close()


@router.get("/standards")
def get_standards():
    """Get indexed IEC standard documents."""
    conn = _get_conn()
    try:
        docs = conn.execute(
            "SELECT * FROM standard_documents ORDER BY standard_name"
        ).fetchall()

        return {"standards": [dict(d) for d in docs]}
    finally:
        conn.close()


@router.get("/history")
def get_history(type_filter: Optional[str] = Query(None), limit: int = Query(20, le=100)):
    """Get combined run history across all types."""
    conn = _get_conn()
    try:
        entries = []

        if not type_filter or type_filter == "reconcile":
            runs = conn.execute(
                "SELECT id, started_at as date, 'reconcile' as type, status, health_score as score FROM reconciliation_runs ORDER BY started_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            entries.extend([dict(r) for r in runs])

        if not type_filter or type_filter == "audit":
            audits = conn.execute(
                "SELECT id, run_at as date, 'audit' as type, standard_name as status, compliance_pct as score FROM compliance_audits ORDER BY run_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            entries.extend([dict(a) for a in audits])

        if not type_filter or type_filter == "features":
            reports = conn.execute(
                "SELECT id, run_at as date, 'features' as type, complete_count || '/' || demo_item_count as status, total_score_available as score FROM feature_status_reports ORDER BY run_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            entries.extend([dict(r) for r in reports])

        # Sort combined by date
        entries.sort(key=lambda x: x.get("date", ""), reverse=True)
        return {"history": entries[:limit]}
    finally:
        conn.close()
