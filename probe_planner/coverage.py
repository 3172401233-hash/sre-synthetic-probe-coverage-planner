"""覆盖分析：计算每个接口的有效覆盖、检测延迟、成本与显式覆盖缺口。"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set, Tuple

from .models import EntryPath, Interface, PlannerConfig, Probe

# 缺口类型
GAP_NO_PROBE = "NO_PROBE"
GAP_SINGLE_FAILURE_DOMAIN = "SINGLE_FAILURE_DOMAIN"
GAP_CRITICAL_ENTRY_LOW_ASSURANCE = "CRITICAL_ENTRY_LOW_ASSURANCE"
GAP_ENTRY_UNCOVERED = "ENTRY_UNCOVERED"
GAP_FREQUENCY_INSUFFICIENT = "FREQUENCY_INSUFFICIENT"
GAP_COVERAGE_BELOW_SLO = "COVERAGE_BELOW_SLO"


@dataclass(frozen=True)
class Gap:
    """显式覆盖缺口。"""

    kind: str
    interface_id: str
    message: str


@dataclass
class InterfaceCoverage:
    interface_id: str
    probes: List[Probe]
    effective_coverage: float  # 至少一个探针检出真实故障的概率
    expected_detection_latency_seconds: float
    worst_detection_latency_seconds: float
    cost_per_month: float
    gaps: List[Gap] = field(default_factory=list)


def _failure_domains_of(probes):
    # type: (Sequence[Probe]) -> Set[Tuple[str, str]]
    domains = set()
    for probe in probes:
        domains.update(probe.failure_domains)
    return domains


def effective_coverage(probes):
    # type: (Sequence[Probe]) -> float
    """至少一个探针检出故障的概率：1 - Π(漏报率)。"""
    if not probes:
        return 0.0
    miss_all = 1.0
    for probe in probes:
        miss_all *= probe.miss_rate
    return 1.0 - miss_all


def detection_latency(probes):
    # type: (Sequence[Probe]) -> Tuple[float, float]
    """任一探针触发即检出：延迟由最快探针决定。返回 (期望, 最差)。"""
    if not probes:
        return (float("inf"), float("inf"))
    fastest = min(p.interval_seconds for p in probes)
    return (fastest / 2.0, float(fastest))


def single_points_of_dependency(probes_by_interface):
    # type: (Dict[str, Sequence[Probe]]) -> List[Tuple[Tuple[str, str], str]]
    """单点依赖：移除某故障域后，某接口将完全失去检测能力。"""
    all_domains = set()  # type: Set[Tuple[str, str]]
    for probes in probes_by_interface.values():
        all_domains.update(_failure_domains_of(probes))

    spofs = []
    for domain in sorted(all_domains):
        for interface_id, probes in sorted(probes_by_interface.items()):
            survivors = [p for p in probes if domain not in p.failure_domains]
            if probes and not survivors:
                spofs.append((domain, interface_id))
    return spofs


def analyze_interface(
    interface,  # type: Interface
    entries,  # type: Sequence[EntryPath]
    probes,  # type: Sequence[Probe]
    config,  # type: PlannerConfig
):
    # type: (...) -> InterfaceCoverage
    """分析单个接口的探针集合，产出有效覆盖与全部显式缺口。"""
    gaps = []  # type: List[Gap]
    iface_id = interface.id
    probes = list(probes)

    if not probes:
        gaps.append(Gap(GAP_NO_PROBE, iface_id, "接口没有任何探针覆盖"))
        return InterfaceCoverage(
            interface_id=iface_id,
            probes=[],
            effective_coverage=0.0,
            expected_detection_latency_seconds=float("inf"),
            worst_detection_latency_seconds=float("inf"),
            cost_per_month=0.0,
            gaps=gaps,
        )

    # 约束一：同一故障域不能占据全部检测能力
    for domain in sorted(_failure_domains_of(probes)):
        survivors = [p for p in probes if domain not in p.failure_domains]
        if not survivors:
            kind, name = domain
            gaps.append(
                Gap(
                    GAP_SINGLE_FAILURE_DOMAIN,
                    iface_id,
                    "故障域 {}={} 占据全部检测能力，"
                    "其故障将使所有探针同时失效".format(kind, name),
                )
            )

    # 约束二：每个入口都要有探针；关键入口不能仅由低成本探针覆盖
    iface_entries = [e for e in entries if e.interface_id == iface_id]
    for entry in iface_entries:
        entry_probes = [p for p in probes if p.entry_id == entry.id]
        if not entry_probes:
            gaps.append(
                Gap(
                    GAP_ENTRY_UNCOVERED,
                    iface_id,
                    "入口 {} 没有任何探针覆盖".format(entry.id),
                )
            )
            continue
        if entry.critical and not any(
            config.is_critical_grade(p) for p in entry_probes
        ):
            gaps.append(
                Gap(
                    GAP_CRITICAL_ENTRY_LOW_ASSURANCE,
                    iface_id,
                    "关键入口 {} 仅由低成本/高漏报探针覆盖，"
                    "低成本探针不能替代关键入口".format(entry.id),
                )
            )

    # 约束三：频率必须满足 SLO 检测延迟
    expected, worst = detection_latency(probes)
    if worst > interface.slo.max_detection_latency_seconds:
        gaps.append(
            Gap(
                GAP_FREQUENCY_INSUFFICIENT,
                iface_id,
                "最快探针间隔 {}s 超过 SLO 最大检测延迟 {}s".format(
                    int(worst), interface.slo.max_detection_latency_seconds
                ),
            )
        )

    coverage = effective_coverage(probes)
    if coverage < interface.slo.availability_target:
        gaps.append(
            Gap(
                GAP_COVERAGE_BELOW_SLO,
                iface_id,
                "有效覆盖 {:.6f} 低于 SLO 目标 {:.6f}".format(
                    coverage, interface.slo.availability_target
                ),
            )
        )

    return InterfaceCoverage(
        interface_id=iface_id,
        probes=probes,
        effective_coverage=coverage,
        expected_detection_latency_seconds=expected,
        worst_detection_latency_seconds=worst,
        cost_per_month=sum(p.cost_per_month for p in probes),
        gaps=gaps,
    )
