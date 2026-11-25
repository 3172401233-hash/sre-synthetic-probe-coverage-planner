"""探针规划：从候选探针中贪心选择满足约束的低成本子集。

约束：
1. 每个接口至少一个探针，且最快探针满足 SLO 检测延迟；
2. 同一故障域（区域或 DNS）不能占据接口的全部检测能力；
3. 每个入口至少一个探针，关键入口必须有非低成本、低漏报的探针。

无法被候选集合满足的约束不会被静默忽略，而是在分析阶段作为显式缺口输出。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .coverage import Gap, InterfaceCoverage, analyze_interface, single_points_of_dependency
from .models import EntryPath, Interface, PlannerConfig, Probe


@dataclass
class PlanResult:
    coverages: Dict[str, InterfaceCoverage]
    single_points_of_dependency: List
    total_cost_per_month: float
    gaps: List[Gap] = field(default_factory=list)


def _cheapest(candidates):
    # type: (Sequence[Probe]) -> Probe
    return min(candidates, key=lambda p: (p.cost_per_month, p.interval_seconds, p.id))


def _select_for_interface(interface, entries, candidates, config):
    # type: (Interface, Sequence[EntryPath], Sequence[Probe], PlannerConfig) -> List[Probe]
    selected = []  # type: List[Probe]
    remaining = list(candidates)

    def take(pred):
        pool = [p for p in remaining if pred(p)]
        if not pool:
            return None
        probe = _cheapest(pool)
        remaining.remove(probe)
        selected.append(probe)
        return probe

    iface_entries = [e for e in entries if e.interface_id == interface.id]

    # 每轮补一个最能修复当前违例的探针，直到没有可修复的违例
    for _ in range(len(candidates) + 1):
        # 1) 检测延迟：至少一个探针满足 SLO 频率
        if not any(
            p.interval_seconds <= interface.slo.max_detection_latency_seconds
            for p in selected
        ):
            if take(
                lambda p: p.interval_seconds
                <= interface.slo.max_detection_latency_seconds
            ):
                continue
            # 没有满足频率的候选：先保证有探针，缺口由分析阶段显式输出
            if not selected and take(lambda p: True):
                continue

        if not selected:
            if take(lambda p: True):
                continue
            break

        # 2) 入口覆盖与关键入口保障
        fixed = False
        for entry in iface_entries:
            entry_selected = [p for p in selected if p.entry_id == entry.id]
            if not entry_selected:
                if take(lambda p, e=entry: p.entry_id == e.id):
                    fixed = True
                    break
            elif entry.critical and not any(
                config.is_critical_grade(p) for p in entry_selected
            ):
                if take(
                    lambda p, e=entry: p.entry_id == e.id
                    and config.is_critical_grade(p)
                ):
                    fixed = True
                    break
        if fixed:
            continue

        # 3) 故障域冗余：任何单一故障域都不能占据全部检测能力
        domains = set()
        for p in selected:
            domains.update(p.failure_domains)
        dominating = [
            d for d in domains if all(d in p.failure_domains for p in selected)
        ]
        if dominating:
            domain = dominating[0]
            if take(lambda p, d=domain: d not in p.failure_domains):
                continue

        break

    return selected


def plan(
    interfaces,  # type: Sequence[Interface]
    entries,  # type: Sequence[EntryPath]
    candidates,  # type: Sequence[Probe]
    config=None,  # type: PlannerConfig
):
    # type: (...) -> PlanResult
    """规划探针集合并分析每个接口的有效覆盖。"""
    config = config or PlannerConfig()
    coverages = {}  # type: Dict[str, InterfaceCoverage]
    probes_by_interface = {}  # type: Dict[str, List[Probe]]

    for interface in interfaces:
        iface_candidates = [
            p for p in candidates if p.interface_id == interface.id
        ]
        selected = _select_for_interface(
            interface, entries, iface_candidates, config
        )
        probes_by_interface[interface.id] = selected
        coverages[interface.id] = analyze_interface(
            interface, entries, selected, config
        )

    spofs = single_points_of_dependency(probes_by_interface)
    gaps = [gap for cov in coverages.values() for gap in cov.gaps]
    total_cost = sum(cov.cost_per_month for cov in coverages.values())

    return PlanResult(
        coverages=coverages,
        single_points_of_dependency=spofs,
        total_cost_per_month=total_cost,
        gaps=gaps,
    )
