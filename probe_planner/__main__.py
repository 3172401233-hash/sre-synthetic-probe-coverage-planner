"""CLI：读取场景 JSON，输出探针覆盖规划报告。

用法：python -m probe_planner scenario.json
本工具只做离线规划分析，不执行任何真实探测。
"""

import json
import sys

from .models import EntryPath, Interface, PlannerConfig, Probe, SLO
from .planner import plan
from .report import render_text


def load_scenario(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cfg_data = data.get("config", {})
    config = PlannerConfig(
        low_cost_threshold=cfg_data.get("low_cost_threshold", 5.0),
        critical_max_miss_rate=cfg_data.get("critical_max_miss_rate", 0.05),
    )
    interfaces = [
        Interface(
            id=item["id"],
            slo=SLO(
                availability_target=item["slo"]["availability_target"],
                max_detection_latency_seconds=item["slo"][
                    "max_detection_latency_seconds"
                ],
            ),
            critical=item.get("critical", False),
        )
        for item in data.get("interfaces", [])
    ]
    entries = [
        EntryPath(
            id=item["id"],
            interface_id=item["interface_id"],
            critical=item.get("critical", False),
        )
        for item in data.get("entries", [])
    ]
    candidates = [
        Probe(
            id=item["id"],
            interface_id=item["interface_id"],
            entry_id=item["entry_id"],
            region=item["region"],
            dns_zone=item["dns_zone"],
            interval_seconds=item["interval_seconds"],
            cost_per_month=item["cost_per_month"],
            miss_rate=item.get("miss_rate", 0.0),
        )
        for item in data.get("candidates", [])
    ]
    return interfaces, entries, candidates, config


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("用法: python -m probe_planner <scenario.json>\n")
        return 2
    interfaces, entries, candidates, config = load_scenario(argv[1])
    result = plan(interfaces, entries, candidates, config)
    print(render_text(result))
    return 1 if result.gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
