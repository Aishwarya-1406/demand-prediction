from fastapi import APIRouter, Request
from pydantic import BaseModel

from engine.dacdf import load_rules, save_rules

router = APIRouter(prefix="/api", tags=["rules"])


class RulesUpdate(BaseModel):
    rules: dict


@router.get("/business-rules")
def get_rules():
    return load_rules()


@router.post("/business-rules")
def update_rules(body: RulesUpdate):
    save_rules(body.rules)
    return {"status": "saved", "rules": body.rules}
