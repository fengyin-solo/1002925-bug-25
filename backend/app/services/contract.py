"""维保合同业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "contract"
CONTRACT_FIELDS = ["合同编号", "签约单位", "维保范围", "合同金额", "签约日期", "到期日期", "是否续签", "合同状态"]
REQUIRED_FIELDS = ["合同编号", "签约单位", "维保范围", "到期日期"]
ACTION_REQUIRED_FIELDS = ["签约单位", "到期日期"]
STATUS_ORDER = ["待签约", "执行中", "即将到期", "已终止"]
TERMINAL_STATUS = "已终止"
# 动作 -> (目标状态, 允许发起的当前状态)：合同只能按 待签约→执行中→即将到期→已终止 推进，
# 到期续签是即将到期回到执行中的续约回路，已终止是终态，任何动作都不再生效。
ACTION_RULES = {
    "签订合同": ("执行中", ["待签约"]),
    "到期续签": ("执行中", ["即将到期"]),
    "终止合同": ("已终止", ["待签约", "执行中", "即将到期"]),
}
NEGATIVE_ACTIONS: list[str] = []


def _blank(value: Any) -> bool:
    return not str(value or "").strip()


class ContractService:
    def _view(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表、详情、动作结果共用的序列化口径，保证台账与到期提醒读到同一份到期日期。"""
        view = {field: row.get(field) for field in CONTRACT_FIELDS}
        view.update({
            "id": row.get("id"),
            "status": row.get("status"),
            "pending": row.get("pending"),
            "abnormal": row.get("abnormal"),
        })
        return view

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("合同编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._view(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        # 先校必填再落库：缺项时不产生任何记录，避免留下只有半张的单据。
        missing = [field for field in REQUIRED_FIELDS if _blank(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 整张单子的字段都保留，而不是只存必填项。
        entry.update({field: values.get(field) for field in CONTRACT_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["合同状态"] = STATUS_ORDER[0]
        entry["是否续签"] = "否"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._view(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于维保合同可执行范围"
        current = str(entry.get("status") or "")
        if current == TERMINAL_STATUS:
            return None, f"维保合同已终止，「{action}」不再生效：续签与终止冲突时以终止为准"
        target, allowed_sources = ACTION_RULES[action]
        if current not in allowed_sources:
            order = " → ".join(STATUS_ORDER)
            return None, f"当前状态「{current}」不能执行「{action}」，合同需按 {order} 顺序推进"
        submitted = values or {}
        # 签订与续签都是承诺类动作：提交前先校必填，签约单位、到期日期缺哪项就报哪项。
        if action in ("签订合同", "到期续签"):
            missing = []
            if _blank(submitted.get("签约单位") or entry.get("签约单位")):
                missing.append("签约单位")
            # 续签必须随单给出新的到期日期，不能沿用旧日期，否则台账与到期提醒读到的还是同一天。
            expiry = submitted.get("到期日期") if action == "到期续签" else submitted.get("到期日期") or entry.get("到期日期")
            if _blank(expiry):
                missing.append("到期日期")
            if missing:
                return None, f"缺少必填字段：{'、'.join(missing)}"
        # 把随动作提交上来的新条款（如续签后的到期日期）合并进合同，台账与提醒读到的才是同一个日期。
        for field in CONTRACT_FIELDS:
            if field in submitted and not _blank(submitted.get(field)):
                entry[field] = submitted[field]
        if action == "到期续签":
            entry["是否续签"] = "是"
        entry["status"] = target
        entry["合同状态"] = target
        entry["pending"] = target != TERMINAL_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._view(entry), f"维保合同已{action}"
