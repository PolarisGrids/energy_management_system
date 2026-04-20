from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.deps import get_current_user
from app.models.user import User
from app.core.config import settings
from app.services.audit_publisher import publish_audit
from app.services.notification_service import notification_service

router = APIRouter()


class TeamsConfig(BaseModel):
    client_id: str
    tenant_id: str
    enabled: bool


class TeamsAlert(BaseModel):
    title: str
    message: str
    severity: str = "info"


@router.get("/config", response_model=TeamsConfig)
def get_teams_config(_: User = Depends(get_current_user)):
    return TeamsConfig(
        client_id=settings.TEAMS_CLIENT_ID,
        tenant_id=settings.TEAMS_TENANT_ID,
        enabled=settings.TEAMS_ENABLED,
    )


@router.post("/alert")
async def send_teams_alert(payload: TeamsAlert, current_user: User = Depends(get_current_user)):
    ok = notification_service.send_teams_alert(payload.title, payload.message, payload.severity)
    await publish_audit(
        action_type="WRITE",
        action_name="send_teams_alert",
        entity_type="TeamsAlert",
        request_data=payload.model_dump(),
        response_status=200,
        method="POST",
        path="/api/v1/teams/alert",
        user_id=str(current_user.id),
    )
    return {"success": ok, "channel": "teams", "enabled": settings.TEAMS_ENABLED}
