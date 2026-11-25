# sre-synthetic-probe-coverage-planner

合成监控探针覆盖规划工具：根据接口 SLO、入口路径、区域、DNS 依赖、探针频率、
成本和历史漏报率，规划探针集合并计算每个接口的有效覆盖。

> **重要：本工具只做离线规划与覆盖分析，不执行任何真实探测。**
> 它不会发起网络请求、不会真正探测任何接口，所有结论均基于输入的
> 候选探针参数与历史漏报率进行静态计算。

## 兼容环境

- Python 3.8.2+（仅使用标准库，无第三方依赖）

## 问题背景

合成监控在多个区域执行时常见误区：

- 某些区域走不同入口，只探一个入口会漏掉入口级故障；
- 多个探测共用同一 DNS，DNS 故障时所有探针一起失效，
  团队误以为是全局服务故障；
- 节点/区域故障时所有探针同时失败，缺乏故障域维度的冗余设计。

本工具把**区域**和 **DNS 区域**都建模为故障域，规划时强制约束：

1. **同一故障域不能占据全部检测能力** —— 任一区域或 DNS 故障后，
   接口至少还有一个存活探针；
2. **低成本探针不能替代关键入口** —— 关键入口必须至少有一个
   非低成本且历史漏报率低于阈值的探针；
3. **频率必须满足 SLO 检测延迟** —— 最快探针间隔不得超过
   SLO 最大检测延迟；
4. **覆盖缺口必须显式输出** —— 任何无法满足的约束都以
   `Gap` 形式列出，绝不静默忽略。

## 输入模型

| 概念 | 字段 |
| --- | --- |
| `Interface` | `id`、`slo`（可用性目标、最大检测延迟）、`critical` |
| `EntryPath` | `id`、`interface_id`、`critical`（关键入口） |
| `Probe`（候选） | `id`、`entry_id`、`region`、`dns_zone`、`interval_seconds`、`cost_per_month`、`miss_rate`（历史漏报率） |
| `PlannerConfig` | `low_cost_threshold`（低成本阈值）、`critical_max_miss_rate` |

## 输出

- **探针集合**：每个接口选中的探针及其区域/DNS/频率/成本；
- **有效覆盖**：`1 - Π(各探针漏报率)`，即至少一个探针检出故障的概率；
- **检测延迟**：期望（最快间隔 / 2）与最差（最快间隔）；
- **单点依赖**：移除后会使某接口完全失去检测能力的故障域；
- **成本**：每接口与总计的月成本；
- **覆盖缺口**：`NO_PROBE`、`SINGLE_FAILURE_DOMAIN`、
  `CRITICAL_ENTRY_LOW_ASSURANCE`、`ENTRY_UNCOVERED`、
  `FREQUENCY_INSUFFICIENT`、`COVERAGE_BELOW_SLO`。

## 使用

```bash
# 运行示例场景（有缺口时退出码为 1）
python -m probe_planner examples/scenario.json

# 运行测试
python -m unittest
```

场景 JSON 格式见 `examples/scenario.json`，包含 `config`、`interfaces`、
`entries`、`candidates` 四个部分。

## 代码结构

- `probe_planner/models.py` —— 数据模型与规划配置
- `probe_planner/coverage.py` —— 有效覆盖、检测延迟、单点依赖与缺口分析
- `probe_planner/planner.py` —— 贪心探针选择（约束不满足时留给分析层显式报缺口）
- `probe_planner/report.py` —— 文本报告渲染
- `probe_planner/__main__.py` —— CLI 入口
- `tests/` —— 单元测试（共享 DNS、区域故障、频率不足、关键入口、有效覆盖）
