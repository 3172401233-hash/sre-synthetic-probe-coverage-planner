# -*- coding: utf-8 -*-
"""覆盖分析单元测试：共享 DNS、区域故障、频率不足、关键入口与有效覆盖。"""

import unittest

from probe_planner.coverage import (
    GAP_COVERAGE_BELOW_SLO,
    GAP_CRITICAL_ENTRY_LOW_ASSURANCE,
    GAP_FREQUENCY_INSUFFICIENT,
    GAP_SINGLE_FAILURE_DOMAIN,
    analyze_interface,
    detection_latency,
    effective_coverage,
    single_points_of_dependency,
)
from probe_planner.models import EntryPath, Interface, PlannerConfig, Probe, SLO


def make_interface(max_latency=60, target=0.99):
    return Interface(
        id="api",
        slo=SLO(
            availability_target=target,
            max_detection_latency_seconds=max_latency,
        ),
    )


def make_probe(pid, region, dns_zone, interval=30, cost=10.0, miss=0.01,
               entry="e1"):
    return Probe(
        id=pid,
        interface_id="api",
        entry_id=entry,
        region=region,
        dns_zone=dns_zone,
        interval_seconds=interval,
        cost_per_month=cost,
        miss_rate=miss,
    )


class SharedDnsTest(unittest.TestCase):
    """多个区域共用同一 DNS：DNS 故障域占据全部检测能力。"""

    def test_shared_dns_is_single_failure_domain(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="shared-dns"),
            make_probe("p2", region="eu-west-1", dns_zone="shared-dns"),
            make_probe("p3", region="ap-southeast-1", dns_zone="shared-dns"),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_SINGLE_FAILURE_DOMAIN, kinds)
        dns_gaps = [g for g in cov.gaps if "dns=shared-dns" in g.message]
        self.assertEqual(len(dns_gaps), 1)

    def test_shared_dns_is_single_point_of_dependency(self):
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="shared-dns"),
            make_probe("p2", region="eu-west-1", dns_zone="shared-dns"),
        ]
        spofs = single_points_of_dependency({"api": probes})
        self.assertIn((("dns", "shared-dns"), "api"), spofs)
        # 区域不是单点：任一区域故障仍有其他区域存活
        region_spofs = [d for d, _ in spofs if d[0] == "region"]
        self.assertEqual(region_spofs, [])

    def test_split_dns_removes_spof(self):
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a"),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b"),
        ]
        spofs = single_points_of_dependency({"api": probes})
        self.assertEqual(spofs, [])


class RegionalFailureTest(unittest.TestCase):
    """区域故障：冗余探针应保证任一区域故障后仍有检测能力。"""

    def test_region_failure_leaves_coverage(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a"),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b"),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        self.assertEqual(cov.gaps, [])
        # 模拟区域故障：移除 us-east-1 后仍有探针
        survivors = [
            p for p in probes if ("region", "us-east-1") not in p.failure_domains
        ]
        self.assertTrue(survivors)
        self.assertGreater(effective_coverage(survivors), 0.0)

    def test_single_region_is_gap(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a"),
            make_probe("p2", region="us-east-1", dns_zone="dns-b"),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_SINGLE_FAILURE_DOMAIN, kinds)
        region_gaps = [g for g in cov.gaps if "region=us-east-1" in g.message]
        self.assertEqual(len(region_gaps), 1)


class FrequencyTest(unittest.TestCase):
    """频率不足：最快探针间隔超过 SLO 检测延迟时必须显式报缺口。"""

    def test_insufficient_frequency(self):
        interface = make_interface(max_latency=60)
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a",
                       interval=300),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b",
                       interval=600),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_FREQUENCY_INSUFFICIENT, kinds)
        self.assertEqual(cov.worst_detection_latency_seconds, 300.0)

    def test_sufficient_frequency_has_no_gap(self):
        interface = make_interface(max_latency=60)
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a", interval=30),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b", interval=60),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        self.assertNotIn(GAP_FREQUENCY_INSUFFICIENT, [g.kind for g in cov.gaps])
        self.assertEqual(cov.expected_detection_latency_seconds, 15.0)

    def test_detection_latency_empty(self):
        expected, worst = detection_latency([])
        self.assertEqual(expected, float("inf"))
        self.assertEqual(worst, float("inf"))


class CriticalEntryTest(unittest.TestCase):
    """低成本探针不能替代关键入口。"""

    def test_low_cost_only_on_critical_entry_is_gap(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api", critical=True)]
        probes = [
            make_probe("cheap1", region="us-east-1", dns_zone="dns-a",
                       cost=1.0),
            make_probe("cheap2", region="eu-west-1", dns_zone="dns-b",
                       cost=2.0),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_CRITICAL_ENTRY_LOW_ASSURANCE, kinds)

    def test_high_miss_rate_on_critical_entry_is_gap(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api", critical=True)]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a",
                       cost=10.0, miss=0.5),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b",
                       cost=10.0, miss=0.5),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_CRITICAL_ENTRY_LOW_ASSURANCE, kinds)

    def test_critical_grade_probe_satisfies_entry(self):
        interface = make_interface()
        entries = [EntryPath(id="e1", interface_id="api", critical=True)]
        probes = [
            make_probe("good", region="us-east-1", dns_zone="dns-a",
                       cost=10.0, miss=0.01),
            make_probe("cheap", region="eu-west-1", dns_zone="dns-b",
                       cost=1.0, miss=0.2),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertNotIn(GAP_CRITICAL_ENTRY_LOW_ASSURANCE, kinds)


class EffectiveCoverageTest(unittest.TestCase):
    def test_effective_coverage_combines_miss_rates(self):
        probes = [make_probe("p1", "r1", "d1", miss=0.1),
                  make_probe("p2", "r2", "d2", miss=0.2)]
        self.assertAlmostEqual(effective_coverage(probes), 1 - 0.1 * 0.2)

    def test_effective_coverage_empty(self):
        self.assertEqual(effective_coverage([]), 0.0)

    def test_coverage_below_slo_is_gap(self):
        interface = make_interface(target=0.999999)
        entries = [EntryPath(id="e1", interface_id="api")]
        probes = [
            make_probe("p1", region="us-east-1", dns_zone="dns-a", miss=0.5),
            make_probe("p2", region="eu-west-1", dns_zone="dns-b", miss=0.5),
        ]
        cov = analyze_interface(interface, entries, probes, PlannerConfig())
        kinds = [g.kind for g in cov.gaps]
        self.assertIn(GAP_COVERAGE_BELOW_SLO, kinds)


if __name__ == "__main__":
    unittest.main()
