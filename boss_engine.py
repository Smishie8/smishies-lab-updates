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


# PlayerBattleModel 0.60.1302 formation/tactic observations.
# Each five-hero tactic uses five of the six grid coordinates.  Role placement
# frequencies strongly identify rows 1/2/3 as Front/Mid/Back respectively.
TACTIC_SLOT_MASKS_1302 = {
    11: [11,21,22,31,32],
    12: [11,12,21,31,32],
    13: [11,12,21,22,31],
    14: [11,21,22,31,32],
    15: [11,12,21,31,32],
    16: [11,21,22,31,32],
    17: [11,21,22,31,32],
    18: [11,12,21,31,32],
    19: [11,21,22,31,32],
}

TACTIC_POSITION_LANES_1302 = {
    11:"front",12:"front",
    21:"mid",22:"mid",
    31:"back",32:"back",
}

TACTIC_POSITION_ROLE_EVIDENCE_1302 = {
    11: {"Tank":974,"Support":199,"DPS mêlée":139},
    12: {"DPS mêlée":50,"Tank":8,"Support":1},
    21: {"DPS mêlée":1149,"DPS distance":204,"Support":41},
    22: {"DPS mêlée":872,"DPS distance":289,"Support":155},
    31: {"DPS distance":827,"Support":484,"DPS mêlée":18},
    32: {"Support":813,"DPS distance":460,"DPS mêlée":49},
}

# Revalidated against the uploaded PlayerBattleModel.dat on 2026-09-18.
# Across 1,423 decoded five-member snapshots every tactic ID below has exactly
# one observed position mask.  This proves the ID -> mask mapping for this
# dataset.  The Front/Mid/Back labels remain a strongly-supported interpretation
# from role placement frequencies, not a decoded enum name from the game.
TACTIC_OBSERVATION_COUNTS_1302 = {
    11: 1041,
    12: 7,
    13: 15,
    14: 32,
    15: 7,
    16: 66,
    17: 173,
    18: 33,
    19: 49,
}

TACTIC_EVIDENCE_1302 = {
    "mask_mapping": "proven_in_PlayerBattleModel_sample",
    "id_name_mapping": "proven_from_successive_PlayerBattleModel_captures",
    "lane_names": "strongly_probable_from_role_distribution",
    "class_bonuses": "proven_from_ingame_ui",
    "xy_coordinates": "not_found",
    "aggro_formula": "not_decoded",
    "snapshot_count": 1423,
}


# In-game UI evidence supplied on 2026-09-18.
# Class icons are explicit in the tactic cards:
# shield=Tank, sword=Melee, bow=Ranged, cross=Support.
TACTIC_CLASS_ICON_MAP = {
    "shield": "Tank",
    "sword": "DPS mêlée",
    "bow": "DPS distance",
    "cross": "Support",
}

# Names, masks and level-1 bonuses visible in-game.  Names are intentionally
# NOT bound to tactic IDs yet when several IDs share the same mask.
# "conditional_class" means the bonus is only granted when the hero class
# matches the icon displayed by the game for that lane.
TACTIC_CATALOG_INGAME = {
    "Standard": {
        "mask": [11,21,22,31,32],
        "bonuses": {
            "front": [
                {"stat":"def_pct","value":0.05},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [
                {"stat":"atk_pct","value":0.05},
            ],
            "back": [
                {"stat":"heal_amount_pct","value":0.03},
                {"stat":"shield_value_pct","value":0.03},
            ],
        },
    },
    "Mur de Pierre": {
        "mask": [11,12,21,31,32],
        "bonuses": {
            "front": [
                {"stat":"def_pct","value":0.05},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [{"stat":"combo_speed_points","value":15}],
            "back": [{"stat":"skill_recovery_points","value":15}],
        },
    },
    "Tour": {
        "mask": [11,12,21,22,31],
        "bonuses": {
            "front": [
                {"stat":"damage_taken_pct","value":-0.015},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [{"stat":"atk_pct","value":0.05}],
            "back": [{"stat":"mana_gen_points","value":15}],
        },
        "id_match": {"tactic_id":13,"confidence":"strongly_probable_unique_mask"},
    },
    "Phalange": {
        "mask": [11,12,21,31,32],
        "bonuses": {
            "front": [
                {"stat":"damage_taken_pct","value":-0.015},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [
                {"stat":"skill_recovery_points","value":15},
                {"stat":"mana_gen_points","value":15,"conditional_class":"Support"},
            ],
            "back": [
                {"stat":"combo_speed_points","value":15},
                {"stat":"atk_pct","value":0.05},
            ],
        },
    },
    "Tireur d’élite": {
        "mask": [11,21,22,31,32],
        "bonuses": {
            "front": [
                {"stat":"damage_taken_pct","value":-0.015},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [
                {"stat":"accuracy","value":15},
                {"stat":"atk_pct","value":0.05},
            ],
            "back": [
                {"stat":"accuracy","value":15},
                {"stat":"skill_speed_points","value":15},
            ],
        },
    },
    "Avant-garde": {
        "mask": [11,21,22,31,32],
        "bonuses": {
            "front": [
                {"stat":"resistance","value":30},
                {"stat":"def_pct","value":0.05},
            ],
            "mid": [
                {"stat":"combo_speed_points","value":15},
                {"stat":"crit_rate","value":0.03},
            ],
            "back": [{"stat":"skill_speed_points","value":15}],
        },
    },
    "Fer de lance": {
        "mask": [11,21,22,31,32],
        "bonuses": {
            "front": [
                {"stat":"hp_pct","value":0.25},
                {"stat":"mana_gen_points","value":15},
            ],
            "mid": [{"stat":"atk_pct","value":0.05}],
            "back": [
                {"stat":"skill_recovery_points","value":15},
                {"stat":"atk_pct","value":0.05,"conditional_class":"DPS distance"},
            ],
        },
    },
    "Siège": {
        "mask": [11,21,22,31,32],
        "bonuses": {
            "front": [
                {"stat":"hp_pct","value":0.25},
                {"stat":"resistance","value":30},
            ],
            "mid": [
                {"stat":"skill_recovery_points","value":15},
                {"stat":"atk_pct","value":0.05},
            ],
            "back": [{"stat":"mana_gen_points","value":15}],
        },
    },
    "Artillerie": {
        "mask": [11,12,21,31,32],
        "bonuses": {
            "front": [
                {"stat":"def_pct","value":0.05},
                {"stat":"hp_pct","value":0.25},
            ],
            "mid": [
                {"stat":"skill_speed_points","value":15},
                {"stat":"heal_amount_pct","value":0.03,"conditional_class":"Support"},
                {"stat":"shield_value_pct","value":0.03,"conditional_class":"Support"},
            ],
            "back": [
                {"stat":"atk_pct","value":0.05},
                {"stat":"def_ignore_pct","value":0.015,"conditional_class":"DPS distance"},
            ],
        },
    },
}

TACTIC_NAME_GROUPS_BY_MASK = {
    (11,21,22,31,32): ["Standard","Tireur d’élite","Avant-garde","Fer de lance","Siège"],
    (11,12,21,31,32): ["Mur de Pierre","Phalange","Artillerie"],
    (11,12,21,22,31): ["Tour"],
}


# Exact tactic ID -> in-game name mapping, validated from successive
# PlayerBattleModel.dat captures after selecting each tactic in-game.
TACTIC_ID_NAME_1302 = {
    11: "Standard",
    12: "Mur de Pierre",
    13: "Tour",
    14: "Avant-garde",
    15: "Phalange",
    16: "Fer de lance",
    17: "Siège",
    18: "Artillerie",
    19: "Tireur d’élite",
}

TACTIC_NAME_ID_1302 = {name: tid for tid, name in TACTIC_ID_NAME_1302.items()}

for _tid, _name in TACTIC_ID_NAME_1302.items():
    _row = TACTIC_CATALOG_INGAME.get(_name)
    if _row is not None:
        _row["tactic_id"] = _tid
        _row["id_match"] = {"tactic_id": _tid, "confidence": "proven_from_PlayerBattleModel_capture"}


def tactic_slot_mask(tactic_id: int) -> List[int]:
    """Return only an observed mask; never silently substitute another tactic."""
    try:
        row=TACTIC_SLOT_MASKS_1302.get(int(tactic_id))
        return list(row) if row else []
    except Exception:
        return []


def tactic_lane(position: int) -> str:
    """Observed row interpretation. Unknown positions stay explicitly unknown."""
    try:return TACTIC_POSITION_LANES_1302.get(int(position),"unknown")
    except Exception:return "unknown"


# Damage coefficients collected from the in-game Ulgorim 16 skill descriptions
# during the earlier calibration pass.  They are intentionally kept separate
# from the StaticData timing extraction above.
# IMPORTANT: coefficients below are still provisional.  Timings are extracted
# from StaticData, but these damage coefficients must not be promoted to
# game-exact until their source/formula is independently revalidated.
ULGORIM_DAMAGE_MODEL_CONFIDENCE = "proxy/provisional"

ULGORIM_DAMAGE_MODEL = {
    "s1": {
        "phase": 1,
        "normal_atk_pct": 25.0,
        "putrefaction_atk_pct": 0.0,
        "targeting": "2_farthest",
        "corruption_add": 1,
        "stun_s": 8.0,
        "remove_buffs_first_application": 2,
    },
    "s2": {
        "normal_atk_pct": 70.0,
        "putrefaction_atk_pct": 30.0,
        "targeting": "all",
        "corruption_add": 1,
    },
    "auto1": {
        "normal_atk_pct": 3.0,
        "putrefaction_atk_pct": 2.0,
        "targeting": "single",
    },
    "auto2": {
        "normal_atk_pct": 3.0,
        "putrefaction_atk_pct": 2.0,
        "targeting": "single",
        "ultimate_mana_reduction_pct": 1.5,
    },
    "auto3": {
        "normal_atk_pct": 3.0,
        "putrefaction_atk_pct": 2.0,
        "targeting": "aoe_13m",
    },
}


def _incoming_damage_multiplier(defense: float) -> float:
    d=max(0.0,float(defense or 0.0))
    return 1.0/(1.0 + 0.0001696*d + 0.00000001245*d*d)


def _living_indices(states):
    return [i for i,s in enumerate(states) if s.get("alive")]


def _lane_rank(lane: str) -> int:
    return {"front":0,"mid":1,"back":2}.get(str(lane or "").strip().lower(),1)


def _weighted_lane_target(states: List[dict], seed: int,
                          lane_weights: Optional[Dict[str,float]]=None) -> List[int]:
    """Deterministic weighted target proxy until the game's exact aggro formula is decoded."""
    weights={"front":5.0,"mid":2.0,"back":1.0}
    if lane_weights:
        for k,v in lane_weights.items():
            try: weights[str(k).lower()]=max(0.0,float(v))
            except Exception: pass
    alive=_living_indices(states)
    if not alive:return []
    pool=[]
    total=0.0
    for i in alive:
        lane=str(states[i].get("lane") or "mid").lower()
        w=max(0.0,weights.get(lane,1.0))
        total+=w
        pool.append((i,total))
    if total<=0:return [alive[0]]
    # Stable pseudo-random value without importing Python's randomized hash().
    x=((seed*1103515245 + 12345) & 0x7fffffff)/2147483648.0
    pick=x*total
    for i,edge in pool:
        if pick<edge:return [i]
    return [pool[-1][0]]


def _proxy_targets(action_key: str, states: List[dict], seed: int=1,
                   lane_weights: Optional[Dict[str,float]]=None) -> List[int]:
    """Lane-aware target resolver.

    Exact position coordinates / aggro code are not decoded yet.  Known spatial
    semantics are preserved:
      - S2: all living heroes.
      - S1 'two farthest': Back > Mid > Front, then stable slot order.
      - single-target autos: weighted toward Front by configurable provisional weights.
      - Auto3 13 m AoE: still all living heroes until XY coordinates are available.
    """
    alive=_living_indices(states)
    if not alive:return []
    if action_key=="s2":return alive
    if action_key=="s1":
        return sorted(alive,key=lambda i:(_lane_rank(states[i].get("lane")),states[i].get("slot",0)),reverse=True)[:2]
    if action_key in ("auto1","auto2"):
        return _weighted_lane_target(states,seed,lane_weights)
    if action_key=="auto3":return alive
    return []


def simulate_opening_survival(profile: BossProfile, team: List[dict], boss_atk: float,
                              duration: Optional[float]=None,
                              lane_weights: Optional[Dict[str,float]]=None) -> dict:
    """Apply Ulgorim's validated opening damage to real HP/DEF team states.

    V1 deliberately stops after the validated opening.  It does not yet model
    movement, Putrefaction periodic ticks, healing/shields, Warchant threshold
    transitions, or recurring post-opening boss AI.
    """
    if profile.key!="ulgorim":
        return {"enabled":False,"reason":"Aucun modèle de survie boss enregistré."}

    states=[]
    missing=[]
    for slot,m in enumerate(team or [],1):
        hp=m.get("health")
        defense=m.get("defense")
        if hp is None or defense is None or float(hp or 0)<=0:
            missing.append(m.get("name") or f"slot {slot}")
            continue
        max_hp=float(hp)
        states.append({
            "slot":slot,
            "name":m.get("name") or f"slot {slot}",
            "max_hp":max_hp,
            "hp":max_hp,
            "defense":float(defense or 0),
            "resistance":float(m.get("resistance") or 0),
            "source":m.get("source") or "unknown",
            "lane":str(m.get("lane") or "mid").strip().lower(),
            "position":m.get("position"),
            "tactic_slot":m.get("tactic_slot",slot),
            "class":m.get("class") or "",
            "tactic_id":m.get("tactic_id"),
            "tactic_name":m.get("tactic_name"),
            "tactic_bonuses_applied":list(m.get("tactic_bonuses_applied") or []),
            "tactic_bonuses_skipped":list(m.get("tactic_bonuses_skipped") or []),
            "tactic_stats_before":dict(m.get("tactic_stats_before") or {}),
            "tactic_stats_after":dict(m.get("tactic_stats_after") or {}),
            "atk":float(m.get("atk") or 0),
            "accuracy":float(m.get("accuracy") or 0),
            "crit_rate":float(m.get("crit_rate") or 0),
            "combo_speed":float(m.get("combo_speed") or 0),
            "skill_speed":float(m.get("skill_speed") or 0),
            "skill_recovery":float(m.get("skill_recovery") or 0),
            "mana_gen":float(m.get("mana_gen") or 0),
            "damage_taken_pct":float(m.get("damage_taken_pct") or 0),
            "heal_amount_pct":float(m.get("heal_amount_pct") or 0),
            "shield_value_pct":float(m.get("shield_value_pct") or 0),
            "def_ignore_pct":float(m.get("def_ignore_pct") or 0),
            "alive":True,
            "death_s":None,
            "corruption":0,
            "damage_taken":0.0,
        })

    if not states:
        return {
            "enabled":False,
            "reason":"Aucun membre de l'équipe ne possède des PV/DEF exploitables.",
            "missing_members":missing,
        }

    timeline=build_opening_timeline(profile)
    events=[]
    atk=float(boss_atk or 0)
    for ev in timeline:
        if duration is not None and float(ev["start_s"])>float(duration):
            break
        key=ev["action"]
        model=ULGORIM_DAMAGE_MODEL.get(key)
        if not model:
            events.append({
                "time":ev["start_s"],"action":key,"label":ev["label"],
                "type":"mechanic","targets":[],"note":"Aucun dégât direct appliqué dans cette version.",
            })
            continue
        target_ids=_proxy_targets(key,states,seed=int(ev["n"] or 1),lane_weights=lane_weights)
        rows=[]
        raw_pct=float(model.get("normal_atk_pct") or 0)+float(model.get("putrefaction_atk_pct") or 0)
        raw=atk*raw_pct/100.0
        for idx in target_ids:
            s=states[idx]
            if not s.get("alive"):
                continue
            defense_mult=_incoming_damage_multiplier(s["defense"])
            tactic_taken_mult=max(0.0,1.0+float(s.get("damage_taken_pct") or 0.0))
            dmg=raw*defense_mult*tactic_taken_mult
            before=s["hp"]
            s["hp"]=max(0.0,before-dmg)
            s["damage_taken"]+=dmg
            if model.get("corruption_add"):
                s["corruption"]+=int(model["corruption_add"])
            if s["hp"]<=0 and s["alive"]:
                s["alive"]=False
                s["death_s"]=float(ev["start_s"])
            rows.append({
                "name":s["name"],
                "hp_before":before,
                "damage":dmg,
                "defense_multiplier":defense_mult,
                "tactic_damage_taken_multiplier":tactic_taken_mult,
                "hp_after":s["hp"],
                "corruption":s["corruption"],
                "dead":not s["alive"],
            })
        events.append({
            "time":float(ev["start_s"]),
            "action":key,
            "label":ev["label"],
            "type":"damage",
            "raw_pct_atk":raw_pct,
            "raw_damage":raw,
            "targets":rows,
            "targeting":model.get("targeting"),
            "target_proxy":model.get("targeting") not in ("all",),
            "stun_s":float(model.get("stun_s") or 0),
            "ultimate_mana_reduction_pct":float(model.get("ultimate_mana_reduction_pct") or 0),
        })

    return {
        "enabled":True,
        "scope":"opening_only",
        "boss_atk":atk,
        "team":[
            {
                **s,
                "hp_pct":(s["hp"]/s["max_hp"] if s["max_hp"] else 0.0),
            }
            for s in states
        ],
        "events":events,
        "missing_members":missing,
        "targeting_validated":False,
        "lane_weights":lane_weights or {"front":5.0,"mid":2.0,"back":1.0},
        "targeting_note":"S2 est exact. S1 respecte Back > Mid > Front pour approximer les 2 plus éloignés. Les autos mono-cible utilisent encore des poids provisoires Front/Mid/Back tant que l'aggro exacte n'est pas décodée.",
        "not_yet_modeled":[
            "positions / distances réelles",
            "ticks périodiques de Putréfaction",
            "soins et boucliers",
            "mort / résurrection côté héros",
            "phase Warchant déclenchée par les PV du boss",
            "rotation récurrente après l'ouverture",
            "effets élémentaires sur les dégâts entrants",
        ],
    }


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
