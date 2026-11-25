"""合成监控探针覆盖规划工具。

只做规划与覆盖分析，不执行任何真实探测。
"""

from .models import SLO, EntryPath, Interface, Probe, PlannerConfig
from .coverage import Gap, InterfaceCoverage, analyze_interface
from .planner import PlanResult, plan

__all__ = [
    "SLO",
    "EntryPath",
    "Interface",
    "Probe",
    "PlannerConfig",
    "Gap",
    "InterfaceCoverage",
    "analyze_interface",
    "PlanResult",
    "plan",
]
