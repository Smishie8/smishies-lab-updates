"""Dynamic boss engine foundations for Smishie's Lab.

The boss layer is data-first: timings come from the game's StaticData and are
kept separate from mechanics so the simulation never invents animation times.
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


# Extracted directly from static-data 0.60.1302, BOSS_OGR049 SkillConfig.
# Q32.32 values are kept at the decoded precision.  "lancement_s" is the
# unavailable/locked action time: pre_cast + cast + EndCastRequiredTime.
ULGORIM_TIMINGS_1302 = {
    "s1": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 15.0,
        "cooldown_s": 18.0,
        "cout_mana": 0.0,
        "pre_cast_s": 4.633333683013916,
        "cast_s": 1.3666672706604004,
        "fin_s": 2.566667079925537,
        "fin_obligatoire_s": 2.566667079925537,
        "lancement_s": 8.566668033599854,
        "animation_totale_s": 8.566668033599854,
        "cooldown_reductible": False,
        "commence_en_cooldown": False,
        "cooldown_initial_s": 0.0,
        "lancable_en_mouvement": False,
    },
    "s2": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 15.0,
        "cooldown_s": 10.0,
        "cout_mana": 0.0,
        "pre_cast_s": 1.8333334922790527,
        "cast_s": 0.0,
        "fin_s": 0.633333683013916,
        "fin_obligatoire_s": 0.633333683013916,
        "lancement_s": 2.4666671752929688,
        "animation_totale_s": 2.4666671752929688,
        "cooldown_reductible": False,
        "commence_en_cooldown": False,
        "cooldown_initial_s": 0.0,
        "lancable_en_mouvement": False,
    },
    "s3": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 3.0,
        "cooldown_s": 27.0,
        "cout_mana": 0.0,
        "pre_cast_s": 2.133333444595337,
        "cast_s": 0.0,
        "fin_s": 0.33333325386047363,
        "fin_obligatoire_s": 0.3333333134651184,
        "lancement_s": 2.4666667580604553,
        "animation_totale_s": 2.4666666984558105,
        "cooldown_reductible": False,
        "commence_en_cooldown": False,
        "cooldown_initial_s": 0.0,
        "lancable_en_mouvement": False,
    },
    "auto1": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 1.0,
        "enchainement_s": 1.1666669845581055,
        "animation_s": 1.1666667461395264,
        "reset_combo_s": 3.0,
    },
    "auto2": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 1.0,
        "enchainement_s": 1.2000000476837158,
        "animation_s": 1.2000001668930054,
        "reset_combo_s": 3.0,
    },
    "auto3": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 1.0,
        "enchainement_s": 2.0999999046325684,
        "animation_s": 2.1000001430511475,
        "reset_combo_s": 3.0,
    },
    "warchant": {
        "source": "StaticData 0.60.1302 / BOSS_OGR049 SkillConfig",
        "range": 0.0,
        "slide_distance": 2.0,
        "cooldown_s": 0.0,
        "cout_mana": 1000.0,
        "pre_cast_s": 0.5,
        "cast_s": 30.0,
        "fin_s": 3.4666669368743896,
        "fin_obligatoire_s": 3.4666669368743896,
        "lancement_s": 33.96666693687439,
        "animation_totale_s": 33.96666693687439,
        "cooldown_reductible": False,
        "commence_en_cooldown": False,
        "cooldown_initial_s": 0.0,
        "lancable_en_mouvement": False,
    },
}

# Summon cadence extracted from their own CharacterConfig / SkillConfig.
ULGORIM_SUMMON_TIMINGS_1302 = {
    "OGR049_Healing_Totem1": {
        "source": "StaticData 0.60.1302",
        "auto1": {
            "range": 50.0,
            "enchainement_s": 1.2666666507720947,
            "animation_s": 1.2666666507720947,
            "reset_combo_s": 3.0,
        },
    },
    "OGR049_Damage_Totem": {
        "source": "StaticData 0.60.1302",
        "auto1": {
            "range": 50.0,
            "enchainement_s": 3.0,
            "animation_s": 3.0,
            "reset_combo_s": 3.0,
        },
    },
    # The level script uses this asset for the four Warchant/Power Totems.
    "OGR049_Healing_Totem2": {
        "source": "StaticData 0.60.1302",
        "role": "Warchant / Power Totem",
        "note": "Continuous-heal behaviour is script-driven; no fake auto cadence is assigned.",
    },
}


ULGORIM = BossProfile(
    key="ulgorim",
    display_name="Ulgorim",
    asset_code="BOSS_OGR049",
    config_id=17259670027575675,
    # StaticData exposes three real combo/auto SkillConfigs for BOSS_OGR049.
    opening=["s1", "s2", "s3", "auto1", "auto2", "auto3"],
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
                "invoque 2 × Healing Totem (OGR049_Healing_Totem1)",
                "invoque 1 × Damage Totem (OGR049_Damage_Totem)",
            ],
        ),
        "warchant": BossActionSpec(
            "warchant", "Chant de guerre", None, "phase boss",
            [
                "boss invulnérable pendant la phase",
                "invoque 4 × OGR049_Healing_Totem2 (Power Totems)",
                "soin du boss via Power Totems",
                "buff ATQ selon PV réellement restaurés",
            ],
        ),
        "auto1": BossActionSpec("auto1", "Auto 1"),
        "auto2": BossActionSpec("auto2", "Auto 2"),
        "auto3": BossActionSpec("auto3", "Auto 3"),
    },
    summons={
        "healing_totem": "OGR049_Healing_Totem1",
        "damage_totem": "OGR049_Damage_Totem",
        "power_totem": "OGR049_Healing_Totem2",
    },
    phases=[
        {"trigger_hp_pct": 66.0, "action": "warchant"},
        {"trigger_hp_pct": 33.0, "action": "warchant"},
    ],
    notes=[
        "Corruption disparaît à la mort de la cible.",
        "Le boss est immunisé aux contrôles / knock / pull / launch.",
        "StaticData 0.60.1302 contient 3 autos réelles pour BOSS_OGR049, pas 5.",
        "La priorité de recast après l'ouverture n'est pas encore déclarée comme validée.",
    ],
)


BOSS_PROFILES = {
    "ulgorim": ULGORIM,
    "ulgorim 16": ULGORIM,
}


def get_boss_profile(name: str) -> Optional[BossProfile]:
    return BOSS_PROFILES.get(str(name or "").strip().lower())


def timing_data_for(profile: BossProfile) -> dict:
    if profile.key == "ulgorim":
        return {k: dict(v) for k, v in ULGORIM_TIMINGS_1302.items()}
    return {}


def summon_timing_data_for(profile: BossProfile) -> dict:
    if profile.key == "ulgorim":
        return {k: dict(v) for k, v in ULGORIM_SUMMON_TIMINGS_1302.items()}
    return {}


def action_lock_time(timing: dict) -> Optional[float]:
    if not isinstance(timing, dict):
        return None
    if timing.get("lancement_s") is not None:
        return float(timing["lancement_s"])
    if timing.get("enchainement_s") is not None:
        return float(timing["enchainement_s"])
    return None


def build_opening_timeline(profile: BossProfile, timing_data: Optional[dict] = None) -> List[dict]:
    """Build only the validated opening sequence.

    We intentionally stop after the opening.  Recast priority and exact cooldown
    start semantics still need to be locked before producing a recurring boss AI
    schedule.
    """
    timing_data = timing_data or timing_data_for(profile)
    out = []
    now = 0.0
    for index, key in enumerate(profile.opening, 1):
        spec = profile.actions.get(key)
        timing = timing_data.get(key) or {}
        lock = action_lock_time(timing)
        if lock is None:
            break
        anim = timing.get("animation_totale_s", timing.get("animation_s", lock))
        out.append({
            "n": index,
            "action": key,
            "label": spec.label if spec else key,
            "start_s": now,
            "available_s": now + float(lock),
            "lock_s": float(lock),
            "animation_s": float(anim) if anim is not None else None,
            "cooldown_s": spec.cooldown_s if spec else None,
        })
        now += float(lock)
    return out


def profile_as_dict(profile: BossProfile, timing_data: Optional[dict] = None) -> dict:
    timing_data = timing_data or timing_data_for(profile)
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
        "opening_timeline": build_opening_timeline(profile, timing_data),
        "opening_end_s": (build_opening_timeline(profile, timing_data)[-1]["available_s"]
                          if build_opening_timeline(profile, timing_data) else 0.0),
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
        "summon_timings": summon_timing_data_for(profile),
        "phases": list(profile.phases),
        "notes": list(profile.notes),
        "timings_resolved": len(missing) == 0,
        "missing_timings": missing,
        "resolved_timings": resolved,
        "timing_source": "StaticData 0.60.1302",
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
