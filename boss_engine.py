"""Dynamic boss engine foundations for Smishie's Lab.

V1 is deliberately data-first: no guessed animation durations are inserted.
Boss mechanics and asset mappings can be registered independently from the
exact action timings extracted from StaticData.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class BossActionSpec:
    key: str
    label: str
    cooldown_s: Optional[float] = None
    target: str = ""
    effects: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BossProfile:
    key: str
    display_name: str
    asset_code: str
    config_id: int
    opening: List[str]
    actions: Dict[str, BossActionSpec]
    summons: Dict[str, str]
    phases: List[Dict[str, Any]]
    notes: List[str] = field(default_factory=list)


ULGORIM = BossProfile(
    key="ulgorim",
    display_name="Ulgorim",
    asset_code="BOSS_OGR049",
    config_id=17259670027575675,
    opening=["s1", "s2", "s3", "auto1", "auto2", "auto3", "auto4", "auto5"],
    actions={
        "s1": BossActionSpec(
            "s1", "Brise-nuage", 18.0, "2 plus éloignés / saut AoE",
            [
                "dégâts",
                "corruption: stun 8 s",
                "retire 2 buffs",
                "putréfaction",
                "phase 2: saut AoE 12 m",
                "phase 2: -35 mana Ult",
            ],
        ),
        "s2": BossActionSpec(
            "s2", "Fureur ogresse", 10.0, "toute l'équipe",
            ["dégâts", "+1 stack Corruption", "putréfaction"],
        ),
        "s3": BossActionSpec(
            "s3", "Sceaux anciens", 27.0, "invocations",
            [
                "invoque Healing Totem 1",
                "invoque Healing Totem 2",
                "invoque Damage Totem",
            ],
        ),
        "warchant": BossActionSpec(
            "warchant", "Chant de guerre", None, "phase boss",
            [
                "boss invulnérable pendant la phase",
                "invoque 4 Power Totems",
                "soin du boss via Power Totems",
                "buff ATQ selon PV réellement restaurés",
            ],
        ),
        "auto1": BossActionSpec("auto1", "Auto 1"),
        "auto2": BossActionSpec("auto2", "Auto 2"),
        "auto3": BossActionSpec("auto3", "Auto 3"),
        "auto4": BossActionSpec("auto4", "Auto 4"),
        "auto5": BossActionSpec("auto5", "Auto 5"),
    },
    summons={
        "healing_totem_1": "OGR049_Healing_Totem1",
        "healing_totem_2": "OGR049_Healing_Totem2",
        "damage_totem": "OGR049_Damage_Totem",
        "power_totem": "Power Totem",
    },
    phases=[
        {"trigger_hp_pct": 66.0, "action": "warchant"},
        {"trigger_hp_pct": 33.0, "action": "warchant"},
    ],
    notes=[
        "Corruption disparaît à la mort de la cible.",
        "Le boss est immunisé aux contrôles / knock / pull / launch.",
        "Les timings exacts doivent venir du StaticData; aucune durée d'animation n'est inventée.",
    ],
)


BOSS_PROFILES = {
    "ulgorim": ULGORIM,
    "ulgorim 16": ULGORIM,
}


def get_boss_profile(name: str) -> Optional[BossProfile]:
    return BOSS_PROFILES.get(str(name or "").strip().lower())


def profile_as_dict(profile: BossProfile, timing_data: Optional[dict] = None) -> dict:
    timing_data = timing_data or {}
    resolved = {}
    missing = []
    for key in profile.opening:
        row = timing_data.get(key)
        if row:
            resolved[key] = row
        else:
            missing.append(key)
    return {
        "key": profile.key,
        "display_name": profile.display_name,
        "asset_code": profile.asset_code,
        "config_id": profile.config_id,
        "opening": list(profile.opening),
        "actions": {
            k: {
                "key": v.key,
                "label": v.label,
                "cooldown_s": v.cooldown_s,
                "target": v.target,
                "effects": list(v.effects),
                "timing": timing_data.get(k),
            }
            for k, v in profile.actions.items()
        },
        "summons": dict(profile.summons),
        "phases": list(profile.phases),
        "notes": list(profile.notes),
        "timings_resolved": len(missing) == 0,
        "missing_timings": missing,
        "resolved_timings": resolved,
    }


def validate_timing_payload(profile: BossProfile, timing_data: dict) -> dict:
    """Validate exact boss action timing data without inventing fallbacks."""
    problems = []
    for key in profile.opening:
        row = timing_data.get(key)
        if not isinstance(row, dict):
            problems.append(f"{key}: timing manquant")
            continue
        chain = row.get("enchainement_s")
        anim = row.get("animation_s")
        launch = row.get("lancement_s")
        if chain is None and launch is None:
            problems.append(f"{key}: enchaînement/lancement manquant")
        if anim is None and row.get("animation_totale_s") is None:
            problems.append(f"{key}: animation manquante")
    return {"ok": not problems, "problems": problems}
