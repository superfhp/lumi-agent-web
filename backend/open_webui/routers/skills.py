import logging
import os
from typing import Optional

import httpx
from open_webui.models.groups import Groups
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import get_async_session
from open_webui.models.skills import (
    SkillForm,
    SkillModel,
    SkillResponse,
    SkillUserResponse,
    SkillAccessResponse,
    SkillAccessListResponse,
    Skills,
)
from open_webui.models.access_grants import AccessGrants
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_permission, filter_allowed_access_grants

from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)

PAGE_ITEM_COUNT = 30

REMOTE_SKILLS_API_URL = os.environ.get(
    'HERMES_SKILLS_API_URL', 'http://172.16.217.143:8642/v1/hermes/skills'
).rstrip('/')
REMOTE_SKILLS_API_KEY = os.environ.get('HERMES_SKILLS_API_KEY', 'Asdf@1234')
REMOTE_SKILLS_API_TIMEOUT = float(os.environ.get('HERMES_SKILLS_API_TIMEOUT', '30'))

router = APIRouter()


def _remote_skills_headers() -> dict[str, str]:
    headers = {'Accept': 'application/json'}
    if REMOTE_SKILLS_API_KEY:
        headers['Authorization'] = f'Bearer {REMOTE_SKILLS_API_KEY}'
    return headers


def _normalize_remote_skill(item: dict) -> dict:
    skill_id = item.get('id') or item.get('name') or ''
    category = item.get('category')
    meta = item.get('meta') if isinstance(item.get('meta'), dict) else {}
    if category and 'tags' not in meta:
        meta = {**meta, 'tags': [category] if not isinstance(category, list) else category}

    user = item.get('user') or {
        'id': 'hermes-skill-service',
        'name': 'Hermes Agent',
        'role': 'user',
        'email': 'hermes-agent@local',
    }

    return {
        'id': skill_id,
        'user_id': item.get('user_id') or user['id'],
        'name': item.get('name') or skill_id,
        'description': item.get('description'),
        'content': item.get('content', ''),
        'meta': meta or {'tags': []},
        'is_active': item.get('is_active', item.get('enabled', True)),
        'access_grants': item.get('access_grants', []),
        'updated_at': item.get('updated_at', 0),
        'created_at': item.get('created_at', 0),
        'user': user,
    }


async def _fetch_remote_skills() -> list[dict]:
    async with httpx.AsyncClient(timeout=REMOTE_SKILLS_API_TIMEOUT) as client:
        response = await client.get(REMOTE_SKILLS_API_URL, headers=_remote_skills_headers())
        response.raise_for_status()

    payload = response.json()
    if isinstance(payload, dict):
        if isinstance(payload.get('data'), list):
            return payload['data']
        if isinstance(payload.get('items'), list):
            return payload['items']
    if isinstance(payload, list):
        return payload

    return []


############################
# GetSkills
############################


@router.get('/', response_model=list[SkillUserResponse])
async def get_skills(
    request: Request,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    remote_skills = await _fetch_remote_skills()
    return [SkillUserResponse(**_normalize_remote_skill(skill)) for skill in remote_skills]


############################
# GetSkillList
############################


@router.get('/list', response_model=SkillAccessListResponse)
async def get_skill_list(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    limit = PAGE_ITEM_COUNT

    page = max(1, page)
    skip = (page - 1) * limit

    remote_skills = await _fetch_remote_skills()

    if query:
        query_lower = query.lower()
        remote_skills = [
            skill
            for skill in remote_skills
            if query_lower in str(skill.get('name', '')).lower()
            or query_lower in str(skill.get('description', '')).lower()
            or query_lower in str(skill.get('id', skill.get('name', ''))).lower()
            or query_lower in str(skill.get('category', '')).lower()
        ]

    total = len(remote_skills)
    remote_skills = remote_skills[skip : skip + limit]

    return SkillAccessListResponse(
        items=[
            SkillAccessResponse(
                **_normalize_remote_skill(skill),
                write_access=True,
            )
            for skill in remote_skills
        ],
        total=total,
    )


############################
# ExportSkills (Remote API)
############################


@router.get('/export', response_model=list[SkillModel])
async def export_skills(
    request: Request,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Export skills from remote API"""
    remote_skills = await _fetch_remote_skills()
    return [SkillModel(**_normalize_remote_skill(skill)) for skill in remote_skills]


############################
# GetSkillById (Remote API)
############################


@router.get('/id/{id}', response_model=Optional[SkillAccessResponse])
async def get_skill_by_id(id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)):
    """Get skill from remote API by ID"""
    remote_skills = await _fetch_remote_skills()
    skill_data = next((s for s in remote_skills if s.get('id') == id or s.get('name') == id), None)
    
    if skill_data:
        return SkillAccessResponse(
            **_normalize_remote_skill(skill_data),
            write_access=True,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# ToggleSkillById (Remote API)
############################


class ToggleSkillRequest(BaseModel):
    name: str
    enabled: bool


@router.put('/toggle', response_model=Optional[SkillModel])
async def toggle_skill_by_id(
    form_data: ToggleSkillRequest,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Toggle skill state via remote API"""
    try:
        toggle_url = f"{REMOTE_SKILLS_API_URL}/toggle"
        async with httpx.AsyncClient(timeout=REMOTE_SKILLS_API_TIMEOUT) as client:
            response = await client.put(
                toggle_url,
                headers=_remote_skills_headers(),
                json={'name': form_data.name, 'enabled': form_data.enabled}
            )
            response.raise_for_status()
        
        result = response.json()
        if isinstance(result, dict):
            return SkillModel(**_normalize_remote_skill(result))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Invalid response from remote API'),
            )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ERROR_MESSAGES.NOT_FOUND,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(f'Error toggling skill: {e}'),
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(f'Error toggling skill: {str(e)}'),
        )
