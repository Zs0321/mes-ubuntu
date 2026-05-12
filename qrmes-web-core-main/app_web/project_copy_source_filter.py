from __future__ import annotations

from typing import Callable, Iterable, Mapping, Sequence


SPECIALIZED_PROJECT_PRODUCT_TYPE_SETS = (
    frozenset({"油泵电机总成", "行驶电机总成"}),
    frozenset({"电控二合一"}),
    frozenset({"行驶二合一电控总成", "油泵二合一电控总成", "独立VCU"}),
)


def extract_product_type_names(config: Mapping | None) -> list[str]:
    if not isinstance(config, Mapping):
        return []

    raw_product_types = config.get("productTypes")
    if not isinstance(raw_product_types, Sequence) or isinstance(raw_product_types, (str, bytes)):
        raw_product_types = config.get("product_types")

    if not isinstance(raw_product_types, Sequence) or isinstance(raw_product_types, (str, bytes)):
        return []

    names: list[str] = []
    for item in raw_product_types:
        if not isinstance(item, Mapping):
            continue
        type_name = str(item.get("typeName") or item.get("type_name") or "").strip()
        if type_name:
            names.append(type_name)
    return names


def is_specialized_copy_source_project(config: Mapping | None) -> bool:
    type_names = frozenset(extract_product_type_names(config))
    if not type_names:
        return False
    return type_names in SPECIALIZED_PROJECT_PRODUCT_TYPE_SETS


def filter_copy_source_projects(
    project_names: Iterable[str],
    get_project_config: Callable[[str], Mapping | None],
) -> list[str]:
    filtered: list[str] = []

    for raw_name in project_names or []:
        project_name = str(raw_name or "").strip()
        if not project_name:
            continue

        config = get_project_config(project_name)
        type_names = extract_product_type_names(config)
        if not type_names:
            continue

        filtered.append(project_name)

    return filtered
