"""维保合同接口：维护维保合同，覆盖签订合同、到期续签、终止合同等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contract import EXPIRING_DAYS
from app.services.contract import ContractService

router = APIRouter(prefix="/api/contract", tags=["维保合同"])

service = ContractService()

LIST_FIELDS = ["合同编号", "签约单位", "维保范围", "合同金额", "签约日期", "到期日期", "是否续签", "合同状态"]
STATUSES = ["待签约", "执行中", "即将到期", "已终止"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按合同编号检索"),
    status: str | None = Query(default=None, description="待签约、执行中、即将到期、已终止"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按合同编号与状态过滤维保合同列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"合同状态只支持：{'、'.join(STATUSES)}")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/expiring")
def expiring_entries() -> dict[str, Any]:
    """到期提醒：与台账共用同一状态/到期日期口径，避免两处读到的日期不一致。"""
    items, total = service.expiring_entries()
    return {"module": "contract", "days": EXPIRING_DAYS, "total": total, "items": items}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出维保合同清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "contract", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条维保合同明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"维保合同 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条维保合同，缺字段时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="维保合同已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条维保合同执行签订合同、到期续签、终止合同；不允许的动作会被拦下并说明原因。

    续签时把新的到期日期等表单字段放在 payload.values 里一并提交，服务端先校必填再落状态。
    """
    action = str(payload.values.get("action") or "").strip()
    values = {key: value for key, value in payload.values.items() if key != "action"}
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
