"""
权限来源链路解释（用于管理端展示）

目标：
- 给每个 permission 返回 role 默认、群组 allow/deny（区分同步/本地）、用户覆写，以及最终结果来源层级。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def build_permission_explanations(
    *,
    permission_values: List[str],
    evaluated: Dict[str, bool],
    role_permissions: Set[str],
    user_overrides: Dict[str, str],
    group_infos: List[Dict[str, Any]],
    group_id_to_meta: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Args:
        permission_values: 要解释的 permission value 列表（例如 Permission 枚举的 .value）
        evaluated: 最终评估结果 {perm_value: bool}
        role_permissions: 角色默认允许的 perm_value 集合
        user_overrides: 用户显式覆写 {perm_value: 'allow'|'deny'}
        group_infos: user_service.get_group_permissions_for_user_with_source(user_id) 返回
        group_id_to_meta: group_id -> {id,name,display_name,is_local,...}
    """

    # Build perm -> sources
    ds_allow: Dict[str, List[Dict[str, Any]]] = {}
    ds_deny: Dict[str, List[Dict[str, Any]]] = {}
    local_allow: Dict[str, List[Dict[str, Any]]] = {}
    local_deny: Dict[str, List[Dict[str, Any]]] = {}

    for info in group_infos or []:
        gid = info.get("group_id")
        is_local = bool(info.get("is_local", False))
        perms = info.get("permissions") or {}
        meta = dict(group_id_to_meta.get(gid) or {})
        meta.setdefault("id", gid)
        meta.setdefault("is_local", is_local)

        for perm_value, effect in perms.items():
            if effect not in ("allow", "deny"):
                continue
            if is_local:
                if effect == "allow":
                    local_allow.setdefault(perm_value, []).append(meta)
                else:
                    local_deny.setdefault(perm_value, []).append(meta)
            else:
                if effect == "allow":
                    ds_allow.setdefault(perm_value, []).append(meta)
                else:
                    ds_deny.setdefault(perm_value, []).append(meta)

    explanations: List[Dict[str, Any]] = []
    for perm_value in permission_values:
        role_default = perm_value in role_permissions
        override = user_overrides.get(perm_value)

        sources = {
            "synology_groups_allow": ds_allow.get(perm_value, []),
            "synology_groups_deny": ds_deny.get(perm_value, []),
            "local_groups_allow": local_allow.get(perm_value, []),
            "local_groups_deny": local_deny.get(perm_value, []),
        }

        effective_source = "none"
        if override in ("allow", "deny"):
            effective_source = "user_override"
        elif sources["local_groups_allow"] or sources["local_groups_deny"]:
            effective_source = "local_group"
        elif sources["synology_groups_allow"] or sources["synology_groups_deny"]:
            effective_source = "synology_group"
        elif role_default:
            effective_source = "role_default"

        explanations.append(
            {
                "value": perm_value,
                "has_permission": bool(evaluated.get(perm_value, False)),
                "role_default": role_default,
                "user_override": override,
                "group_sources": sources,
                "effective_source": effective_source,
            }
        )

    return explanations

