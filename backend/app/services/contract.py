"""维保合同业务规则：状态流转、字段校验与筛选口径都收在这里。

状态口径（台账与到期提醒共用同一份派生逻辑，保证两处读到的到期日期/状态一致）：
- 待签约：登记后尚未签订；
- 执行中：已签订，且距到期日超过 EXPIRING_DAYS 天；
- 即将到期：已签订，距到期日不超过 EXPIRING_DAYS 天（含已过期但未终止的）；
- 已终止：人工执行「终止合同」，终止优先级最高，终止后不再参与续签与到期派生。

动作权限：
- 签订合同：仅「待签约」可执行，按顺序推进到「执行中」；
- 到期续签：仅「即将到期」可执行，回到「执行中」，必须提交新的到期日期且至少覆盖 30 天；
- 终止合同：非「已终止」均可执行；终止与续签冲突时以终止为准，已终止合同不许再续签。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "contract"
# 登记与签订时都必须齐备的字段；到期日期缺了就无法判断是否即将到期，因此也列入必填。
REQUIRED_FIELDS = ["合同编号", "签约单位", "维保范围", "到期日期"]
SIGNABLE_FIELDS = ["合同编号", "签约单位", "维保范围", "合同金额", "签约日期", "到期日期", "是否续签"]
STATUS_ORDER = ["待签约", "执行中", "即将到期", "已终止"]
PENDING_SIGN, ACTIVE, EXPIRING, TERMINATED = STATUS_ORDER
# 「签订合同」只能由待签约推进；「到期续签」只在即将到期时开放，并回到执行中。
ACTION_TRANSITIONS = {"签订合同": (PENDING_SIGN, ACTIVE), "到期续签": (EXPIRING, ACTIVE)}
EXPIRING_DAYS = 30


def _parse_date(value: Any) -> date | None:
    """把 YYYY-MM-DD 字符串解析成日期；空值或非法格式返回 None，由调用方提示。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class ContractService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._sync(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("合同编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._sync(entry)

    def expiring_entries(self, *, days: int = EXPIRING_DAYS) -> tuple[list[dict[str, Any]], int]:
        """到期提醒口径：已签订且未终止、距到期日不超过 days 天（含已过期）的合同。

        与列表页走同一份状态派生，保证同一合同在台账与提醒里的到期日期完全一致。
        """
        today = date.today()
        rows = []
        for row in store.rows(MODULE):
            entry = self._sync(dict(row))
            if entry["status"] != EXPIRING:
                continue
            expiry = _parse_date(entry.get("到期日期"))
            if expiry is not None and expiry <= today + timedelta(days=days):
                rows.append(entry)
        rows.sort(key=lambda row: str(row.get("到期日期") or ""))
        return rows, len(rows)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，补齐后再提交"
        if _parse_date(values.get("到期日期")) is None:
            return None, "到期日期格式不正确，应为 YYYY-MM-DD"

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in SIGNABLE_FIELDS:
            value = values.get(field)
            if str(value or "").strip():
                entry[field] = str(value).strip()
        entry.setdefault("是否续签", "否")
        entry["status"] = PENDING_SIGN
        rows.append(entry)
        return self._sync(entry), ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        if action not in (*ACTION_TRANSITIONS, "终止合同"):
            return None, f"动作「{action}」不属于维保合同可执行范围"

        # 终止优先级最高：任何状态都可终止，但终止后不允许再执行任何动作（含续签）。
        if entry.get("status") == TERMINATED:
            return None, "该合同已终止，不能再续签或变更状态"
        if action == "终止合同":
            entry["status"] = TERMINATED
            return self._sync(entry), "维保合同已终止"

        expected, target = ACTION_TRANSITIONS[action]
        current = self._sync(entry)["status"]
        # 状态必须按 待签约 → 执行中 → 即将到期 顺序推进，不能越级，也不能对执行中的合同直接续签。
        if current != expected:
            return None, f"当前状态为「{current}」，不能执行「{action}」；请按 待签约 → 执行中 → 即将到期 的顺序推进"

        # 动作提交前先校必填：签订/续签时缺签约单位或到期日期一律拦下，并说明缺哪一项。
        # 提交了的键即使是空白也算缺失；未提交的键才用合同上已有的值兜底。
        problems: list[str] = []
        for field in ("签约单位", "到期日期"):
            submitted = field in values
            raw = values.get(field) if submitted else entry.get(field)
            if not str(raw or "").strip():
                problems.append("签约单位" if field == "签约单位" else "到期日期")
        if problems:
            return None, f"缺少必填字段：{'、'.join(problems)}，补齐后再提交"
        expiry = _parse_date(values.get("到期日期") or entry.get("到期日期"))
        if expiry is None:
            return None, "到期日期格式不正确，应为 YYYY-MM-DD"

        # 续签必须给出新的到期日期，且至少覆盖 EXPIRING_DAYS 天，否则续签完仍会立刻回到即将到期。
        if action == "到期续签":
            min_expiry = date.today() + timedelta(days=EXPIRING_DAYS)
            if expiry <= min_expiry:
                return None, f"续签后的到期日期须晚于 {min_expiry.isoformat()}（至少续签 {EXPIRING_DAYS} 天）"
            entry["是否续签"] = "是"
        if action == "签订合同":
            if not str(values.get("签约日期") or "").strip() and not str(entry.get("签约日期") or "").strip():
                entry["签约日期"] = date.today().isoformat()
            else:
                signed_on = _parse_date(values.get("签约日期") or entry.get("签约日期"))
                if signed_on is not None:
                    entry["签约日期"] = signed_on.isoformat()

        party = values.get("签约单位") or entry.get("签约单位")
        entry["签约单位"] = str(party).strip()
        entry["到期日期"] = expiry.isoformat()
        entry["status"] = target
        return self._sync(entry), f"维保合同已{action}"

    def _sync(self, entry: dict[str, Any]) -> dict[str, Any]:
        """统一台账/详情/提醒三处的数据口径。

        冗余展示键（合同状态、是否续签、到期日期）在这里归一化：合同状态始终以状态机
        派生结果为准，到期日期只有一个来源，避免列表与详情读到不一样的值。
        """
        entry.setdefault("是否续签", "否")
        status = entry.get("status") if entry.get("status") in STATUS_ORDER else PENDING_SIGN

        # 已终止是终态，终止优先于续签与到期派生，不再回退到即将到期。
        if status != TERMINATED and status != PENDING_SIGN:
            expiry = _parse_date(entry.get("到期日期"))
            if expiry is not None and expiry <= date.today() + timedelta(days=EXPIRING_DAYS):
                status = EXPIRING

        entry["status"] = status
        entry["合同状态"] = status
        entry["pending"] = status != TERMINATED
        entry["abnormal"] = status == EXPIRING
        return entry
