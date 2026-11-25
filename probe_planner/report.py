"""规划结果的可读报告渲染。"""

from typing import List

from .planner import PlanResult


def render_text(result):
    # type: (PlanResult) -> str
    lines = []  # type: List[str]
    lines.append("=== 合成监控探针覆盖规划报告（离线分析，不执行真实探测） ===")
    lines.append("")

    for interface_id in sorted(result.coverages):
        cov = result.coverages[interface_id]
        lines.append("接口: {}".format(interface_id))
        if cov.probes:
            lines.append("  探针集合:")
            for p in sorted(cov.probes, key=lambda x: x.id):
                lines.append(
                    "    - {} 入口={} 区域={} DNS={} 间隔={}s "
                    "成本=${:.2f}/月 历史漏报率={:.3f}".format(
                        p.id,
                        p.entry_id,
                        p.region,
                        p.dns_zone,
                        p.interval_seconds,
                        p.cost_per_month,
                        p.miss_rate,
                    )
                )
        else:
            lines.append("  探针集合: （空）")
        lines.append("  有效覆盖: {:.6f}".format(cov.effective_coverage))
        lines.append(
            "  检测延迟: 期望={:.1f}s 最差={:.1f}s".format(
                cov.expected_detection_latency_seconds,
                cov.worst_detection_latency_seconds,
            )
        )
        lines.append("  成本: ${:.2f}/月".format(cov.cost_per_month))
        if cov.gaps:
            lines.append("  覆盖缺口:")
            for gap in cov.gaps:
                lines.append("    ! [{}] {}".format(gap.kind, gap.message))
        else:
            lines.append("  覆盖缺口: 无")
        lines.append("")

    lines.append("单点依赖（故障域移除后接口完全失去检测能力）:")
    if result.single_points_of_dependency:
        for (kind, name), interface_id in result.single_points_of_dependency:
            lines.append(
                "  ! {}={} -> 接口 {}".format(kind, name, interface_id)
            )
    else:
        lines.append("  无")
    lines.append("")
    lines.append("总成本: ${:.2f}/月".format(result.total_cost_per_month))
    lines.append(
        "覆盖缺口总数: {}".format(len(result.gaps))
    )
    return "\n".join(lines)
