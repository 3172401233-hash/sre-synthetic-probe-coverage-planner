# -*- coding: utf-8 -*-
"""规划器集成测试：选出的探针集合满足约束，无法满足时缺口显式输出。"""

import unittest

from probe_planner.coverage import (
    GAP_CRITICAL_ENTRY_LOW_ASSURANCE,
    GAP_FREQUENCY_INSUFFICIENT,
    GAP_SINGLE_FAILURE_DOMAIN,
)
from probe_planner.models import EntryPath, Interface, PlannerConfig, Probe, SLO
from probe_planner.planner import plan
from probe_planner.report import render_text


def build_scenario():
    interface = Interface(
        id="api",
        slo=SLO(availability_target=0.99, max_detection_latency_seconds=60),
    )
    entries = [
        EntryPath(id="e-critical", interface_id="api", critical=True),
        EntryPath(id="e-normal", interface_id="api"),
    ]
    candidates = [
        Probe("c1", "api", "e-critical", "us-east-1", "dns-a", 30, 10.0, 0.01),
        Probe("c2", "api", "e-critical", "eu-west-1", "dns-b", 30, 10.0, 0.01),
        Probe("c3", "api", "e-normal", "us-east-1", "dns-a", 60, 4.0, 0.05),
        Probe("c4", "api", "e-normal", "ap-southeast-1", "dns-c", 60, 6.0, 0.02),
    ]
    return [interface], entries, candidates


class PlannerTest(unittest.TestCase):
    def test_plan_selects_redundant_set_without_gaps(self):
        interfaces, entries, candidates = build_scenario()
        result = plan(interfaces, entries, candidates, PlannerConfig())
        self.assertEqual(result.gaps, [])
        self.assertEqual(result.single_points_of_dependency, [])
        cov = result.coverages["api"]
        # 关键入口由非低成本探针覆盖
        critical_probes = [p for p in cov.probes if p.entry_id == "e-critical"]
        self.assertTrue(
            any(PlannerConfig().is_critical_grade(p) for p in critical_probes)
        )
        # 两个入口都被覆盖
        covered_entries = {p.entry_id for p in cov.probes}
        self.assertEqual(covered_entries, {"e-critical", "e-normal"})
        # 成本与报告
        self.assertAlmostEqual(
            result.total_cost_per_month, cov.cost_per_month
        )
        report = render_text(result)
        self.assertIn("api", report)
        self.assertIn("有效覆盖", report)

    def test_plan_surfaces_unfixable_shared_dns(self):
        interface = Interface(
            id="api",
            slo=SLO(availability_target=0.9, max_detection_latency_seconds=60),
        )
        entries = [EntryPath(id="e1", interface_id="api")]
        candidates = [
            Probe("c1", "api", "e1", "us-east-1", "shared-dns", 30, 10.0, 0.01),
            Probe("c2", "api", "e1", "eu-west-1", "shared-dns", 30, 10.0, 0.01),
        ]
        result = plan([interface], entries, candidates, PlannerConfig())
        kinds = [g.kind for g in result.gaps]
        self.assertIn(GAP_SINGLE_FAILURE_DOMAIN, kinds)
        self.assertIn((("dns", "shared-dns"), "api"),
                      result.single_points_of_dependency)

    def test_plan_surfaces_unfixable_frequency(self):
        interface = Interface(
            id="api",
            slo=SLO(availability_target=0.9, max_detection_latency_seconds=30),
        )
        entries = [EntryPath(id="e1", interface_id="api")]
        candidates = [
            Probe("c1", "api", "e1", "us-east-1", "dns-a", 300, 10.0, 0.01),
            Probe("c2", "api", "e1", "eu-west-1", "dns-b", 300, 10.0, 0.01),
        ]
        result = plan([interface], entries, candidates, PlannerConfig())
        kinds = [g.kind for g in result.gaps]
        self.assertIn(GAP_FREQUENCY_INSUFFICIENT, kinds)

    def test_plan_surfaces_low_cost_only_critical_entry(self):
        interface = Interface(
            id="api",
            slo=SLO(availability_target=0.9, max_detection_latency_seconds=60),
        )
        entries = [EntryPath(id="e1", interface_id="api", critical=True)]
        candidates = [
            Probe("cheap1", "api", "e1", "us-east-1", "dns-a", 30, 1.0, 0.01),
            Probe("cheap2", "api", "e1", "eu-west-1", "dns-b", 30, 1.0, 0.01),
        ]
        result = plan([interface], entries, candidates, PlannerConfig())
        kinds = [g.kind for g in result.gaps]
        self.assertIn(GAP_CRITICAL_ENTRY_LOW_ASSURANCE, kinds)

    def test_plan_prefers_cheaper_candidates(self):
        interfaces, entries, candidates = build_scenario()
        result = plan(interfaces, entries, candidates, PlannerConfig())
        cov = result.coverages["api"]
        normal_probes = [p for p in cov.probes if p.entry_id == "e-normal"]
        # e-normal 的冗余覆盖应优先选最便宜的 c3
        self.assertIn("c3", {p.id for p in normal_probes})


if __name__ == "__main__":
    unittest.main()
