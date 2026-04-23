"""
Vaidya — API v1 router
Aggregates all endpoint sub-routers
"""

from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    auth as auth_ep,
    input as input_ep,
    nlp as nlp_ep,
    diagnose as diagnose_ep,
    llm_diagnose as llm_ep,
    triage as triage_ep,
    care as care_ep,
    patients as patients_ep,
    analytics as analytics_ep,
    asha as asha_ep,
)
from app.core.security import rate_limit

api_router = APIRouter(dependencies=[Depends(rate_limit)])

api_router.include_router(auth_ep.router,      prefix="/auth",      tags=["auth"])
api_router.include_router(input_ep.router,     prefix="/input",     tags=["input"])
api_router.include_router(nlp_ep.router,       prefix="/nlp",       tags=["nlp"])
api_router.include_router(diagnose_ep.router,  prefix="/diagnose",  tags=["diagnose"])
api_router.include_router(llm_ep.router,       prefix="/llm",       tags=["llm-diagnosis"])
api_router.include_router(triage_ep.router,    prefix="/triage",    tags=["triage"])
api_router.include_router(care_ep.router,      prefix="/care",      tags=["care"])
api_router.include_router(patients_ep.router,  prefix="/patients",  tags=["patients"])
api_router.include_router(analytics_ep.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(asha_ep.router,      prefix="/asha",      tags=["asha"])
