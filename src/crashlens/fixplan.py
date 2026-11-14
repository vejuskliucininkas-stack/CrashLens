"""Work out what 'Fix everything' will do.

For each problem that needs attention now, take the first fix that actually does
something (runs a tool or cleans up) rather than just opening a Windows page.
Duplicate fixes are merged. If any fix changes Windows, a restore point is made
first so the changes can be undone. Problems with no automatic fix are listed
as things the person needs to do themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crashlens.core.models import Finding
from crashlens.repairs.catalog import REPAIRS, RepairKind
from crashlens.triage import Triage

AUTOMATIC = (RepairKind.TOOL, RepairKind.BUILTIN)
SAFETY_FIRST = "restore_point"
NOT_AUTOMATIC = {"memory_diagnostic"}  # needs a restart - the person decides when


@dataclass
class FixStep:
    repair_id: str
    findings: list[Finding] = field(default_factory=list)


@dataclass
class FixPlan:
    steps: list[FixStep] = field(default_factory=list)
    manual: list[Finding] = field(default_factory=list)

    @property
    def repair_ids(self) -> list[str]:
        return [s.repair_id for s in self.steps]

    def __bool__(self) -> bool:
        return bool(self.steps)


def automatic_fix(f: Finding) -> str | None:
    for rid in f.repair_ids:
        r = REPAIRS.get(rid)
        if r is not None and r.kind in AUTOMATIC and rid not in NOT_AUTOMATIC:
            return rid
    return None


def build_plan(t: Triage) -> FixPlan:
    plan = FixPlan()
    by_id: dict[str, FixStep] = {}
    for f in t.problems:
        rid = automatic_fix(f)
        if rid is None:
            plan.manual.append(f)
            continue
        if rid not in by_id:
            by_id[rid] = FixStep(rid)
            plan.steps.append(by_id[rid])
        by_id[rid].findings.append(f)
    changes_windows = any(
        REPAIRS[s.repair_id].changes_system and REPAIRS[s.repair_id].kind is RepairKind.TOOL
        for s in plan.steps
    )
    if changes_windows and SAFETY_FIRST not in by_id:
        plan.steps.insert(0, FixStep(SAFETY_FIRST))
    return plan
