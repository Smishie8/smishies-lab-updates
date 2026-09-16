from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json
import math
import sqlite3

VALIDATED_DEF_LINEAR = 0.0001696
VALIDATED_DEF_QUADRATIC = 0.0000001245


def damage_received_multiplier(defense: float) -> float:
    """Formule DEF validée lors des tests en jeu."""
    d = max(0.0, float(defense))
    return 1.0 / (
        1.0
        + VALIDATED_DEF_LINEAR * d
        + VALIDATED_DEF_QUADRATIC * d * d
    )


@dataclass
class CombatResult:
    dps: float
    survival_time: float
    fight_duration: float

    useful_heal: float = 0.0
    overheal: float = 0.0
    shield_absorbed: float = 0.0
    damage_prevented: float = 0.0
    extra_casts: float = 0.0
    extra_ults: float = 0.0
    mana_saved_or_gained: float = 0.0
    stun_time_prevented: float = 0.0
    resurrection_count: float = 0.0
    resurrection_hp_restored: float = 0.0
    boss_healing_prevented: float = 0.0
    corruption_resets_from_revive: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def effective_survival(self) -> float:
        return max(0.0, min(float(self.survival_time), float(self.fight_duration)))

    @property
    def combat_output(self) -> float:
        return max(0.0, float(self.dps)) * self.effective_survival


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    weight: float
    description: str


STANDARD_SCENARIOS = [
    Scenario("low_pressure", "Pression faible", 0.20, "Survie facile : surtout valeur offensive."),
    Scenario("medium_pressure", "Pression moyenne", 0.25, "Heal, shield et mitigation deviennent utiles."),
    Scenario("high_pressure", "Pression forte", 0.25, "Morts possibles : survie et résurrection fortement valorisées."),
    Scenario("debuff_boss", "Boss sensible aux malus", 0.15, "Valorise les debuffs réellement appliqués."),
    Scenario("disrupted_fight", "Combat perturbé", 0.15, "Mana, recovery, contrôle, mouvement et interruption."),
]


@dataclass
class SupportEffect:
    skill: str
    name: str
    value: Optional[float] = None
    duration_s: Optional[float] = None
    condition: Optional[str] = None
    category: str = "other"
    source: str = "invokers.db"
    validation: str = "db"


@dataclass
class AdvancedEffect:
    skill: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    validation: str = "provisional"


@dataclass
class SupportProfile:
    name: str
    rarity: str
    faction: str
    element: str
    base_stats: Dict[str, float]
    cast_times: Dict[str, float]
    mana: Dict[str, Any]
    effects: List[SupportEffect] = field(default_factory=list)
    advanced_effects: List[AdvancedEffect] = field(default_factory=list)

    def categories(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.effects:
            out[e.category] = out.get(e.category, 0) + 1
        for e in self.advanced_effects:
            cat = {
                "heal_pct_max_hp": "survival",
                "heal_flat": "survival",
                "revive": "survival",
                "shield": "survival",
                "cleanse": "utility",
                "unkillable": "survival",
            }.get(e.type, "other")
            out[cat] = out.get(cat, 0) + 1
        return out


@dataclass
class ScenarioEvaluation:
    support: str
    scenario_key: str
    base: CombatResult
    with_support: CombatResult

    @property
    def impact_pct(self) -> float:
        return impact_pct(self.base, self.with_support)


@dataclass
class SupportEvaluation:
    support: str
    scenarios: Dict[str, ScenarioEvaluation] = field(default_factory=dict)
    boss_results: Dict[str, ScenarioEvaluation] = field(default_factory=dict)

    @property
    def general_impact_pct(self) -> float:
        return sum(
            self.scenarios[s.key].impact_pct * s.weight
            for s in STANDARD_SCENARIOS
            if s.key in self.scenarios
        )


def impact_pct(base: CombatResult, with_support: CombatResult) -> float:
    b = base.combat_output
    w = with_support.combat_output
    if b <= 0:
        return 0.0 if w <= 0 else math.inf
    return (w / b - 1.0) * 100.0


def hybrid_impact_pct(offensive_gain_pct: float, survival_gain_pct: float) -> float:
    return (
        (1.0 + offensive_gain_pct / 100.0)
        * (1.0 + survival_gain_pct / 100.0)
        - 1.0
    ) * 100.0


def percentile_scores(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 50.0}

    ordered = sorted(values.items(), key=lambda kv: kv[1])
    n = len(ordered)
    out: Dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        v = ordered[i][1]
        while j + 1 < n and ordered[j + 1][1] == v:
            j += 1
        score = 100.0 * ((i + j) / 2.0) / (n - 1)
        for k in range(i, j + 1):
            out[ordered[k][0]] = round(score, 1)
        i = j + 1
    return out


def score_population(
    evaluations: Iterable[SupportEvaluation],
    boss_key: Optional[str] = None,
) -> Dict[str, Dict[str, float]]:
    evs = list(evaluations)

    if boss_key is None:
        impacts = {e.support: e.general_impact_pct for e in evs}
        impact_key = "impact_general_pct"
        score_key = "score_general_100"
    else:
        impacts = {
            e.support: (
                e.boss_results[boss_key].impact_pct
                if boss_key in e.boss_results else 0.0
            )
            for e in evs
        }
        impact_key = "impact_boss_pct"
        score_key = "score_boss_100"

    scores = percentile_scores(impacts)
    return {
        name: {
            impact_key: round(value, 2),
            score_key: scores.get(name, 0.0),
        }
        for name, value in impacts.items()
    }


def useful_heal(missing_hp: float, raw_heal: float) -> tuple[float, float]:
    missing = max(0.0, float(missing_hp))
    raw = max(0.0, float(raw_heal))
    useful = min(missing, raw)
    return useful, max(0.0, raw - useful)


def useful_shield(incoming_damage_while_active: float, shield_value: float) -> float:
    return min(
        max(0.0, float(incoming_damage_while_active)),
        max(0.0, float(shield_value)),
    )


def revive_value(
    max_hp: float,
    hp_restored_pct: float,
    remaining_fight_s: float,
    post_revive_dps: float,
) -> Dict[str, float]:
    return {
        "restored_hp": max(0.0, max_hp) * max(0.0, hp_restored_pct) / 100.0,
        "extra_output_ceiling": max(0.0, remaining_fight_s) * max(0.0, post_revive_dps),
    }


def _max_coeff_row(con: sqlite3.Connection, name: str) -> Dict[str, Any]:
    con.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in con.execute(
            'SELECT * FROM coefficients_raw WHERE lower("Personnage")=lower(?)',
            (name,),
        )
    ]
    if not rows:
        return {}

    crown = [r for r in rows if str(r.get("Niveau skill")) == "♛"]
    if crown:
        return crown[0]

    def lvl(row: Dict[str, Any]) -> int:
        try:
            return int(row.get("Niveau skill") or 0)
        except Exception:
            return -1

    return max(rows, key=lvl)


def _mana_row(con: sqlite3.Connection, name: str) -> Dict[str, Any]:
    con.row_factory = sqlite3.Row
    row = con.execute(
        'SELECT * FROM mana_raw WHERE lower("Personnage")=lower(?)',
        (name,),
    ).fetchone()
    return dict(row) if row else {}


def classify_effect(name: str) -> str:
    n = (name or "").lower()

    if "heal reduction" in n:
        return "anti_heal"

    if any(x in n for x in (
        "atk up", "crit rate up", "crit dmg up", "combo spd up",
        "skill spd up", "def down", "res down", "weaken",
    )):
        return "offense"

    if any(x in n for x in (
        "atk down", "def up", "res up", "shield", "invinc",
        "unkill", "acc down", "pre down",
    )):
        return "survival"

    if any(x in n for x in ("skill recovery", "mana", "cooldown")):
        return "rotation"

    if any(x in n for x in (
        "stun", "freeze", "taunt", "silence", "knock", "pull", "control",
    )):
        return "control"

    return "other"


def load_overrides(path: Optional[str | Path]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_support_profiles_from_db(
    db_path: str | Path,
    overrides_path: Optional[str | Path] = None,
) -> Dict[str, SupportProfile]:
    """
    Charge directement les héros dont role='Support' depuis invokers.db.
    Lecture seule : aucune modification de la DB.
    """
    db_path = Path(db_path)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    overrides = load_overrides(overrides_path)

    heroes = [
        dict(r)
        for r in con.execute(
            """
            SELECT name, role, rarity, faction, element,
                   hp, atk, defense, crit_rate, crit_dmg,
                   accuracy, resistance,
                   combo_speed, skill_speed, skill_recovery, mana_gen,
                   cast_s1, cast_s2, cast_s3, cast_ult
            FROM heroes
            WHERE lower(role)='support'
            ORDER BY name
            """
        )
    ]

    out: Dict[str, SupportProfile] = {}

    for h in heroes:
        name = h["name"]
        row = _max_coeff_row(con, name)
        mana = _mana_row(con, name)

        effects: List[SupportEffect] = []
        for skill, prefix in (
            ("Auto 5", "Auto 5"),
            ("S1", "S1"),
            ("S2", "S2"),
            ("S3", "S3"),
            ("Ult", "Ult"),
        ):
            for idx in (1, 2):
                effect = row.get(f"{prefix} Effet {idx}")
                if effect in (None, ""):
                    continue
                effects.append(
                    SupportEffect(
                        skill=skill,
                        name=str(effect),
                        value=row.get(f"{prefix} Valeur {idx}"),
                        duration_s=row.get(f"{prefix} Durée {idx}"),
                        condition=row.get(f"{prefix} Condition {idx}"),
                        category=classify_effect(str(effect)),
                    )
                )

        advanced: List[AdvancedEffect] = []
        override = overrides.get(name, {})
        for item in override.get("advanced_effects", []):
            params = {
                k: v
                for k, v in item.items()
                if k not in {"skill", "type", "validation"}
            }
            advanced.append(
                AdvancedEffect(
                    skill=item.get("skill", ""),
                    type=item.get("type", ""),
                    params=params,
                    validation=item.get(
                        "validation",
                        override.get("status", "provisional"),
                    ),
                )
            )

        out[name] = SupportProfile(
            name=name,
            rarity=h.get("rarity", ""),
            faction=h.get("faction", ""),
            element=h.get("element", ""),
            base_stats={
                "hp": h.get("hp"),
                "atk": h.get("atk"),
                "def": h.get("defense"),
                "crit_rate": h.get("crit_rate"),
                "crit_dmg": h.get("crit_dmg"),
                "accuracy": h.get("accuracy"),
                "resistance": h.get("resistance"),
                "combo_speed": h.get("combo_speed"),
                "skill_speed": h.get("skill_speed"),
                "skill_recovery": h.get("skill_recovery"),
                "mana_generation": h.get("mana_gen"),
            },
            cast_times={
                "s1": h.get("cast_s1"),
                "s2": h.get("cast_s2"),
                "s3": h.get("cast_s3"),
                "ult": h.get("cast_ult"),
            },
            mana={
                "combo_ult": mana.get("Combo Ult total"),
                "s1_ult": mana.get("S1 Ult"),
                "s2_ult": mana.get("S2 Ult"),
                "s3_ult": mana.get("S3 Ult"),
                "ult_cost": mana.get("Coût Ult connu"),
                "combo_titan": mana.get("Combo Titan calculé")
                    if mana.get("Combo Titan calculé") is not None
                    else mana.get("Combo Titan"),
                "s1_titan": mana.get("S1 Titan calculé")
                    if mana.get("S1 Titan calculé") is not None
                    else mana.get("S1 Titan"),
                "s2_titan": mana.get("S2 Titan calculé")
                    if mana.get("S2 Titan calculé") is not None
                    else mana.get("S2 Titan"),
                "s3_titan": mana.get("S3 Titan calculé")
                    if mana.get("S3 Titan calculé") is not None
                    else mana.get("S3 Titan"),
            },
            effects=effects,
            advanced_effects=advanced,
        )

    con.close()
    return out


ULGORIM_16 = {
    "name": "Ulgorim",
    "tier": 16,
    "level": 100,
    "element": "Feu",
    "hp": 172_800,
    "atk": 744,
    "def": 8_540,
    "pre": 105,
    "res": 475,
    "tolerance_modifier_pct": -60.0,
    "control_immune": True,
    "corruption_cleansable": False,
    "corruption_resets_on_death": True,
    "mechanics": {
        "fureur_ogresse_cd_s": 10.0,
        "brise_nuage_cd_s": 18.0,
        "sceaux_anciens_cd_s": 27.0,
        "war_chant_hp_thresholds_pct": [66.0, 33.0],
        "healing_totem_heal_pct_max_hp_every_1_3s": 1.25,
        "war_chant_power_totems": 4,
        "war_chant_channel_s": 30.0,
        "war_chant_each_totem_total_heal_pct_max_hp": 30.0,
        "putrefaction_tick_pct_target_max_hp_per_stack": 0.5,
    },
}


def boss_mechanic_notes(
    profile: SupportProfile,
    boss: Dict[str, Any] = ULGORIM_16,
) -> List[str]:
    notes: List[str] = []

    for effect in profile.effects:
        n = effect.name.lower()

        if boss.get("control_immune") and effect.category == "control":
            notes.append(
                f"{effect.skill} {effect.name}: valeur boss directe = 0 "
                "(immunité contrôle)."
            )

        if "heal reduction" in n:
            notes.append(
                f"{effect.skill} {effect.name}: très pertinent contre les soins "
                "d'Ulgorim."
            )

        if "atk down" in n or "weaken" in n:
            notes.append(
                f"{effect.skill} {effect.name}: peut réduire la pression entrante."
            )

    for effect in profile.advanced_effects:
        if effect.type == "revive" and boss.get("corruption_resets_on_death"):
            notes.append(
                f"{effect.skill} Revive: le héros revient sans ses anciens "
                "stacks de Corruption."
            )
        if effect.type == "cleanse" and not boss.get("corruption_cleansable", True):
            notes.append(
                f"{effect.skill} Cleanse: ne retire pas la Corruption."
            )

    return notes


def coverage_summary(profile: SupportProfile) -> Dict[str, Any]:
    provisional = sum(
        1 for x in profile.advanced_effects
        if "provisional" in x.validation
    )
    return {
        "support": profile.name,
        "db_effect_count": len(profile.effects),
        "advanced_effect_count": len(profile.advanced_effects),
        "provisional_advanced_effects": provisional,
        "categories": profile.categories(),
        "ready_for_raw_scoring": True,
        "ready_for_precise_survival_scoring": provisional == 0,
    }


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    app_dir = here.parent

    profiles = load_support_profiles_from_db(
        app_dir / "invokers.db",
        here / "support_effect_overrides.json",
    )

    print(f"{len(profiles)} supports chargés.")

    nirvelle = profiles.get("Nirvelle")
    if nirvelle:
        print(json.dumps(
            coverage_summary(nirvelle),
            ensure_ascii=False,
            indent=2,
        ))
        print("Ulgorim 16:")
        for note in boss_mechanic_notes(nirvelle):
            print(" -", note)
