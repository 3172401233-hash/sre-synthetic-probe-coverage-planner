"""数据模型：接口 SLO、入口路径、探针候选与规划配置。

兼容 Python 3.8.2。
"""

from dataclasses import dataclass
from typing import Tuple

# 故障域：("region", 区域名) 或 ("dns", DNS 区域名)。
# 节点故障、区域故障或共享 DNS 故障都会使落在该故障域内的全部探针同时失效。
FailureDomain = Tuple[str, str]


@dataclass(frozen=True)
class SLO:
    """接口级 SLO。"""

    availability_target: float  # 期望可用性，例如 0.999
    max_detection_latency_seconds: int  # 允许的最大故障检测延迟


@dataclass(frozen=True)
class Interface:
    id: str
    slo: SLO
    critical: bool = False


@dataclass(frozen=True)
class EntryPath:
    """接口的入口路径。不同区域/接入方可能走不同入口。"""

    id: str
    interface_id: str
    critical: bool = False  # 关键入口不能被低成本探针单独覆盖


@dataclass(frozen=True)
class Probe:
    """候选探针（规划对象，不对应真实执行的探测）。"""

    id: str
    interface_id: str
    entry_id: str
    region: str
    dns_zone: str  # 该探针解析依赖的 DNS 区域
    interval_seconds: int  # 探测频率（间隔）
    cost_per_month: float
    miss_rate: float = 0.0  # 历史漏报率（假阴性率），0..1

    @property
    def failure_domains(self):
        # type: () -> Tuple[FailureDomain, FailureDomain]
        return (("region", self.region), ("dns", self.dns_zone))


@dataclass(frozen=True)
class PlannerConfig:
    """规划约束配置。"""

    # 月成本低于该值的探针视为低成本探针，不能单独覆盖关键入口
    low_cost_threshold: float = 5.0
    # 覆盖关键入口的探针允许的最大历史漏报率
    critical_max_miss_rate: float = 0.05

    def is_low_cost(self, probe):
        # type: (Probe) -> bool
        return probe.cost_per_month < self.low_cost_threshold

    def is_critical_grade(self, probe):
        # type: (Probe) -> bool
        return (
            not self.is_low_cost(probe)
            and probe.miss_rate <= self.critical_max_miss_rate
        )
