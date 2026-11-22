"""Build optimiser for Attack on Titan Revolution: game data (perks, memories, families), build scoring, the best
build you can equip from what you own, what to get next, and the screen reader for the in-game Perks / Memories
menus (Windows' built-in text recognition).

Perk numbers are from the AOTR wiki (Update 5): "lv0~lv10" = the stat at level +0 and at +10, linear in between.
Scoring = game numbers weighted per playstyle + the macro's rules (must-haves, never-use, preferred). Memory values
are judgement calls where the game gives no plain number (they are written down here so they can be argued with)."""
import difflib
import itertools
import re

# =============================================================================
#  Game data
# =============================================================================
RARITIES = ("Common", "Rare", "Epic", "Legendary", "Mythical", "Divine")
RARITY_COLOR = {"Common": "#9aa3b2", "Rare": "#4fa3ff", "Epic": "#b06cff", "Legendary": "#f0a43a",
                "Mythical": "#ef5a6f", "Divine": "#ecc45c"}
CATEGORIES = ("Core", "Offense", "Defense", "Support")
PLAYSTYLES = ("Shifter", "Thunder Spear", "ODM")


def _p(cat, rarity, stats, text):
    return {"cat": cat, "rarity": rarity, "stats": stats, "text": text}


# stats: key -> (value at +0, value at +10)  (a single number = the same at every level)
PERKS = {
    # ---- Core (Body slot only) ----
    "Enhanced Metabolism": _p("Core", "Common", {"regen": (2, 3)}, ["HEALTH REGEN +2%~3%"]),
    "Critical Hunter": _p("Core", "Rare", {"blade_dur": (7.5, 15), "conserve": (3.75, 7.5)},
                          ["Blade durability / conserve chance +7.5%~15% / 3.75%~7.5%"]),
    "Resilient": _p("Core", "Epic", {"shifts_row": (1, 2), "awaken": (5, 10)},
                    ["Shift up to 1~2 times in a row", "Awakening bar fills 5%~10% faster"]),
    "Solo": _p("Core", "Epic", {"odm_ts_all": (5, 7.5)}, ["ALL ODM/TS stats +5%~7.5%"]),
    "Indefatigable": _p("Core", "Legendary", {"shifts_row": (2, 3), "awaken": (15, 25)},
                        ["Shift up to 2~3 times in a row", "Awakening bar fills 15%~25% faster"]),
    "Perfect Soul": _p("Core", "Legendary", {"odm_ts_all": (7.5, 10)}, ["ALL ODM/TS stats +7.5%~10%"]),
    "Perfect Form": _p("Core", "Legendary", {"odm_dmg": (7.5, 10), "maxdmg_at": (70, 50)},
                       ["ODM/TS DAMAGE +7.5%~10%", "Maximum damage with 70%~50% of your maximum speed"]),
    "Wind Rhapsody": _p("Core", "Legendary", {"dmg_eq": (8, 12)},
                        ["CRIT DAMAGE / 2x~1.67x", "CRIT CHANCE x2~x2.4"]),
    "Flame Rhapsody": _p("Core", "Legendary", {"dmg_eq": (8, 14)},
                         ["CRIT DAMAGE x2~x2.3", "CRIT CHANCE capped to 5%~12.5%"]),
    "Tyrant's Stare": _p("Core", "Legendary", {"dmg_eq": (10, 18)},
                         ["CRIT CHANCE capped to 0%~10%", "15%~25% of CRIT DAMAGE and 25%~40% of CRIT CHANCE become ODM/TS DAMAGE"]),
    "Founder's Blessing": _p("Core", "Mythical", {"shifts_row": (3, 5), "awaken": (25, 35), "aggro": (100, 150),
                                                   "titan_stats": (10, 15)},
                             ["Shift up to 3~5 times in a row", "Awakening bar fills 25%~35% faster",
                              "Aggro range +100~150m", "ALL SHIFTER stats +10%~15%"]),
    "Heavenly Restriction": _p("Core", "Mythical", {"skills_off": 1, "odm_ts_all": (15, 30), "kill_chance": (10, 20),
                                                     "dr": (10, 15)},
                               ["ALL equipped skills are disabled", "ALL ODM/TS stats +15%~30%",
                                "+10%~20% chance to kill titans on injuring them", "DAMAGE RESISTANCE +10%~15%"]),
    "Maximum Firepower": _p("Core", "Mythical", {"spear_count": (2, 4), "spear_speed": (20, 40), "ts_all": (10, 15),
                                                  "no_recoil": 1},
                            ["SPEAR COUNT +2~4", "SPEAR SPEED +20%~40%", "ALL TS stats +10%~15%", "No spear recoil"]),
    "Avatar of Ymir": _p("Core", "Divine", {"shift60": 1, "max_shifts": (4, 7), "awaken": (35, 55), "aggro": (175, 250),
                                             "titan_stats": (20, 35), "shift_aoe": (30, 55), "fear3": 1},
                         ["Shift at 60% Awakening Bar", "Maximum shifts +4~7", "Awakening Bar fills 35%~55% faster",
                          "Aggro range +175~250m", "ALL TITAN stats +20%~35%",
                          "Shifting deals 30%~55% DAMAGE to titans around you", "Every 3 hits in titan form inflicts FEAR"]),
    "Mankind's Strongest": _p("Core", "Divine", {"hook_speed": (30, 40), "odm_all": (20, 35), "maxdmg_at": (45, 20),
                                                  "dmg_eq": (5, 7.5), "bleed": (15, 30)},
                              ["HOOK SPEED +30%~40%", "ALL ODM stats +20%~35%",
                               "Maximum damage with 45%~20% of your maximum speed",
                               "Every 10s alternate +10%~15% DAMAGE / CRIT DAMAGE", "ODM hits do 15%~30% BLEED DAMAGE"]),
    "Sanguine Destroyer": _p("Core", "Divine", {"conserve": (10, 15), "spear_count": (4, 8), "ts_all": (20, 35),
                                                 "no_recoil": 1, "corrosion": 1},
                             ["CONSERVE CHANCE +10%~15%", "SPEAR COUNT +4~8", "ALL TS stats +20%~35%",
                              "Explosions deal 30%~40% less self damage", "No spear recoil", "TS hits inflict CORROSION"]),
    # ---- Offense ----
    "Mighty": _p("Offense", "Common", {"odm_dmg": (5, 10)}, ["ODM/TS DAMAGE +5%~10%"]),
    "Cripple": _p("Offense", "Common", {"crit_dmg": (5, 10)}, ["CRIT DAMAGE +5%~10%"]),
    "Lucky": _p("Offense", "Common", {"crit_chance": (2.5, 5)}, ["CRIT CHANCE +2.5%~5%"]),
    "Hollow": _p("Offense", "Common", {"swing": (2.5, 5)}, ["SWING DURATION +2.5%~5%"]),
    "Forceful": _p("Offense", "Rare", {"odm_dmg": (7.5, 15)}, ["ODM/TS DAMAGE +7.5%~15%"]),
    "Mangle": _p("Offense", "Rare", {"crit_dmg": (10, 20)}, ["CRIT DAMAGE +10%~20%"]),
    "Blessed": _p("Offense", "Rare", {"crit_chance": (5, 10)}, ["CRIT CHANCE +5%~10%"]),
    "Lightweight": _p("Offense", "Rare", {"swing": (5, 10)}, ["SWING DURATION +5%~10%"]),
    "Reckless Abandon": _p("Offense", "Epic", {"crit_dmg": (20, 30), "crit_chance": (-10, -7.5)},
                           ["CRIT DAMAGE +20%~30%", "CRIT CHANCE -10%~-7.5%"]),
    "Flawed Release": _p("Offense", "Epic", {"crit_chance": (10, 20), "crit_dmg": (-30, -25)},
                         ["CRIT CHANCE +10%~20%", "CRIT DAMAGE -30%~-25%"]),
    "Focus": _p("Offense", "Epic", {"crit_chance": (3, 5), "crit_dmg": (10, 15)},
                ["CRIT CHANCE +3%~5%", "CRIT DAMAGE +10%~15%"]),
    "Peerless Strength": _p("Offense", "Epic", {"odm_dmg": (10, 20)}, ["ODM/TS DAMAGE +10%~20%"]),
    "Mutilate": _p("Offense", "Epic", {"crit_dmg": (20, 35)}, ["CRIT DAMAGE +20%~35%"]),
    "Luminous": _p("Offense", "Epic", {"crit_chance": (10, 15)}, ["CRIT CHANCE +10%~15%"]),
    "Speedy": _p("Offense", "Epic", {"swing": (10, 15)}, ["SWING DURATION +10%~15%"]),
    "Butcher": _p("Offense", "Epic", {"limbs_blade": (2, 3)}, ["Blade hits strike 2~3 more limbs"]),
    "Warrior": _p("Offense", "Epic", {"shifter_dmg": (7.5, 15)}, ["SHIFTER DAMAGE +7.5%~15%"]),
    "Bombardier": _p("Offense", "Legendary", {"cannon": (15, 25)}, ["Cannon DAMAGE +15%~25%, AOE and cooldown"]),
    "Unparalleled Strength": _p("Offense", "Legendary", {"odm_dmg": (15, 25)}, ["ODM/TS DAMAGE +15%~25%"]),
    "Eviscerate": _p("Offense", "Legendary", {"crit_dmg": (30, 50)}, ["CRIT DAMAGE +30%~50%"]),
    "Sanctified": _p("Offense", "Legendary", {"crit_chance": (15, 20)}, ["CRIT CHANCE +15%~20%"]),
    "Peerless Focus": _p("Offense", "Legendary", {"crit_chance": (7.5, 10), "crit_dmg": (20, 30)},
                         ["CRIT CHANCE +7.5%~10%", "CRIT DAMAGE +20%~30%"]),
    "Carnifex": _p("Offense", "Legendary", {"limbs_blade": (3, 5), "limbs_ts": (1, 2)},
                   ["Blade / TS hits strike 3~5 / 1~2 more limbs"]),
    "Warchief": _p("Offense", "Legendary", {"shifter_dmg": (12, 20)}, ["SHIFTER DAMAGE +12%~20%"]),
    "Blitzkrieg": _p("Offense", "Mythical", {"cannon": (25, 40)}, ["Cannon DAMAGE +25%~40%, AOE, cooldown, BURN"]),
    "Kengo": _p("Offense", "Mythical", {"odm_dmg": (25, 40), "blade_dur": (10, 20), "conserve": (2.5, 5),
                                         "limbs_blade": (2, 4), "limbs_ts": (1, 2)},
                ["ODM/TS DAMAGE +25%~40%", "Blade durability / conserve +10%~20% / 2.5%~5%",
                 "Blades / TS strike 2~4 / 1~2 more limbs"]),
    "Black Flash": _p("Offense", "Mythical", {"crit_dmg": (30, 60), "dash_iframes": 1, "dmg_eq": (5, 8)},
                      ["Every 1% of SPEED gives +0.3%~0.6% CRIT DAMAGE", "Dashes phase through titans",
                       "Maximum damage on every CRIT"]),
    "Art of War": _p("Offense", "Mythical", {"m1_speed": (7.5, 10), "shifter_dmg": (30, 40)},
                     ["SHIFTER M1 SPEED +7.5%~10%", "SHIFTER DAMAGE +30%~40%"]),
    "Everlasting Flame": _p("Offense", "Mythical", {"blast": (15, 30), "burn": (7.5, 20)},
                            ["BLAST RADIUS +15%~30%", "ODM/TS hits do 7.5%~20% BURN DAMAGE"]),
    "Godforged": _p("Offense", "Divine", {"odm_dmg": (45, 65), "blade_dur": (25, 40), "conserve": (12.5, 20),
                                           "crit_chance": (15, 20), "crit_dmg": (30, 50), "limbs_blade": (3, 6),
                                           "limbs_ts": (2, 4), "hit_stacks": (25, 30)},
                    ["ODM/TS DAMAGE +45%~65%", "Blade durability / conserve +25%~40% / 12.5%~20%",
                     "CRIT CHANCE +15%~20%", "CRIT DAMAGE +30%~50%", "Blades / TS strike 3~6 / 2~4 more limbs",
                     "Each hit +5%~6% DAMAGE / CRIT DAMAGE, up to 5 stacks"]),
    "Stormwrath": _p("Offense", "Divine", {"skill_cd": (20, 30), "shifter_dmg": (50, 65), "punch_speed": (15, 25),
                                            "titan_burst": (15, 25), "skill_dmg": (10, 20)},
                     ["SKILL COOLDOWNS -20%~30%", "SHIFTER DAMAGE +50%~65%", "PUNCHING SPEED +15%~25%",
                      "ALL TITAN stats +15%~25% for 20s after shifting", "Using a skill grants +10%~20% DAMAGE for 5s"]),
    # ---- Defense ----
    "Enduring": _p("Defense", "Common", {"inj_ignore": (1, 2)}, ["Ignore up to 1~2 injuries"]),
    "Fortitude": _p("Defense", "Common", {"health": (10, 25)}, ["HEALTH +10~25"]),
    "Unyielding": _p("Defense", "Rare", {"inj_ignore": (2, 3)}, ["Ignore up to 2~3 injuries"]),
    "Heightened Vitality": _p("Defense", "Rare", {"health": (25, 50)}, ["HEALTH +25~50"]),
    "Tough": _p("Defense", "Rare", {"dr": (3.5, 7.5)}, ["DAMAGE REDUCTION +3.5%~7.5%"]),
    "Protection": _p("Defense", "Rare", {"injury": (5, 10)}, ["INJURY CHANCE -5%~10%"]),
    "Unbreakable": _p("Defense", "Epic", {"inj_ignore": (3, 4)}, ["Ignore up to 3~4 injuries"]),
    "Stalwart Durability": _p("Defense", "Epic", {"health": (50, 75)}, ["HEALTH +50~75"]),
    "Hardy": _p("Defense", "Epic", {"dr": (10, 15)}, ["DAMAGE REDUCTION +10%~15%"]),
    "Safeguard": _p("Defense", "Epic", {"injury": (12, 16)}, ["INJURY CHANCE -12%~16%"]),
    "Invincible": _p("Defense", "Legendary", {"inj_ignore": (3, 5)}, ["Ignore up to 3~5 injuries"]),
    "Font of Vitality": _p("Defense", "Legendary", {"health": (100, 125)}, ["HEALTH +100~125"]),
    "Robust": _p("Defense", "Legendary", {"dr": (20, 27.5)}, ["DAMAGE REDUCTION +20%~27.5%"]),
    "Aegis": _p("Defense", "Legendary", {"injury": (25, 40)}, ["INJURY CHANCE -25%~40%"]),
    "Peerless Constitution": _p("Defense", "Legendary", {"dr": (15, 20), "injury": (15, 25)},
                                ["DAMAGE REDUCTION +15%~20%", "INJURY CHANCE -15%~25%"]),
    "Immortal": _p("Defense", "Mythical", {"injury": (15, 22.5), "health": (100, 125), "dr": (22.5, 30)},
                   ["INJURY CHANCE -15%~22.5%", "HEALTH +100~125", "DAMAGE REDUCTION +22.5%~30%"]),
    "Adaptation": _p("Defense", "Mythical", {"regen": (3, 5), "dmg_taken": (100, 50)},
                     ["HEALTH REGEN +3~5", "Take 2x~1.5x more damage",
                      "Getting hit by an attack twice makes you immune to it (half as good shifted)"]),
    "Eternal": _p("Defense", "Divine", {"health": (150, 200), "dr": (35, 45), "injury": (25, 40), "grab_escape": 1,
                                         "kb_ignore": 1, "dmg_all": (3, 5)},
                  ["HEALTH +150~200", "DAMAGE REDUCTION +35%~45%", "INJURY CHANCE -25%~40%",
                   "Escape grabs with 1~2 fewer inputs", "Ignore 1 killing blow (costs Awakening Bar)",
                   "Getting hit grants +5%~25% DAMAGE on your next hit"]),
    "Foresight": _p("Defense", "Divine", {"inj_ignore": (4, 6), "grab_escape": 1, "dodge": (10, 20),
                                           "skill_power": (20, 35), "dr": (5, 10)},
                    ["Ignore up to 4~6 injuries", "Automatically escape grabs", "10%~20% chance to dodge",
                     "Skills lose I-frames but deal +20%~35% DAMAGE and give 15%~30% resistance",
                     "A killing blow while using a skill doesn't kill you"]),
    # ---- Support ----
    "Gear Beginner": _p("Support", "Common", {"mobility": (0.6, 1.3)}, ["ODM/TS CONTROL +2.5%~5%"]),
    "First Aid": _p("Support", "Common", {"utility": (1, 2)}, ["1~2 more bandages"]),
    "Gear Intermediate": _p("Support", "Rare", {"mobility": (3.1, 4.4)}, ["ODM/TS CONTROL +7.5%~10%, SPEED +5%~7.5%"]),
    "Fully Stocked": _p("Support", "Rare", {"utility": (2, 3)}, ["2~3 more bandages"]),
    "Experimental Shells": _p("Support", "Rare", {"utility": (1, 2)}, ["Acoustic shells and flares +25%~50% area"]),
    "Gear Expert": _p("Support", "Epic", {"mobility": (4.4, 5.6)}, ["ODM/TS CONTROL +10%~12.5%, SPEED +7.5%~10%"]),
    "Siphoning": _p("Support", "Epic", {"utility": (1, 2)}, ["Gas bar +1%~2% per kill"]),
    "Adrenaline": _p("Support", "Epic", {"utility": (2, 3)}, ["8%~18% chance to heal 5%~7.5% missing health per kill"]),
    "Trauma Battery": _p("Support", "Epic", {"utility": (0, 1)}, ["Teammates heal 2.5%~5% when you heal"]),
    "Munitions Expert": _p("Support", "Epic", {"spear_count": (1, 2)}, ["SPEAR COUNT +1~2"]),
    "Gear Master": _p("Support", "Legendary", {"mobility": (5.6, 6.9)}, ["ODM/TS CONTROL +12.5%~15%, SPEED +10%~12.5%"]),
    "Exhumation": _p("Support", "Legendary", {"utility": (2, 3.5)}, ["Gas bar +2%~3.5% per kill"]),
    "Peerless Commander": _p("Support", "Legendary", {"orders": 1, "utility": (0, 1)},
                             ["Allies regen after your orders; orders and flares x1.1~1.25"]),
    "Courage Catalyst": _p("Support", "Legendary", {"orders": 1}, ["Allies' skill cooldowns and control per kill"]),
    "Sixth Sense": _p("Support", "Legendary", {"mobility": (1.9, 2.5), "utility": 1},
                      ["ODM/TS RANGE +7.5%~10%", "See the outlines of all titans"]),
    "Munitions Master": _p("Support", "Legendary", {"spear_count": (2, 4)}, ["SPEAR COUNT +2~4"]),
    "Unwavering Belief": _p("Support", "Mythical", {"skill_cd": (-50, -33)},
                            ["Party skill cooldowns -1.5~2s per kill", "Your SKILL COOLDOWNS x2~x1.5"]),
    "Tatsujin": _p("Support", "Mythical", {"mobility": (12.5, 21.3)},
                   ["ODM/TS CONTROL +15%~25%, SPEED +10%~20%, GAS +10%~15%, RANGE +15%~25%"]),
    "Font of Inspiration": _p("Support", "Mythical", {"orders": 1},
                              ["Orders and flares: cooldowns halved, effects x1.25~1.5, orders mid-air"]),
    "Soulfeed": _p("Support", "Mythical", {"utility": (3, 5)}, ["Gas and health per kill, see all titans"]),
    "Explosive Fortune": _p("Support", "Mythical", {"conserve": (10, 15), "utility": (1, 1.5)},
                            ["CONSERVE CHANCE +10%~15%", "5%~7.5% chance to regain a spear per kill"]),
    "15th Commander": _p("Support", "Divine", {"orders": 1, "utility": (1, 2)},
                         ["Flares and orders: cooldowns halved, effects x1.6~2, cover the whole map, inflict FEAR"]),
    "Branching Paths": _p("Support", "Divine", {"kill_dmg": (0.3, 0.5), "utility": (3, 4)},
                          ["Party DAMAGE +0.3%~0.5% per kill (up to 30%)", "Party gas, health and spears per kill",
                           "See the outlines of all titans"]),
    "Wings of Freedom": _p("Support", "Divine", {"mobility": (26, 36), "odm_ts_all": (10, 15), "dash_iframes": 1,
                                                  "utility": 2},
                           ["ODM/TS GAS +20%~30%, SPEED +25%~35%, CONTROL and RANGE +30%~40%", "ALL ODM/TS stats +10%~15%",
                            "Dashes phase through titans with I-frames", "+1 boost dash, dashing uses 25% less gas"]),
}


def _m(cat, stars, points, text, stats=None):
    """points = (Shifter, Thunder Spear, ODM): what the memory is worth in each playstyle."""
    return {"cat": cat, "stars": stars, "points": dict(zip(PLAYSTYLES, points)), "stats": stats or {}, "text": text}


MEMORIES = {
    "Blood Awakening": _m("Core", 5, (45, 18, 0), "Spawn with a full Awakening Bar; awakened: +50% DAMAGE, +30% resistance"),
    "Elementalist": _m("Core", 5, (6, 10, 10), "ALL status effects empowered (burn, bleed, corrosion, fear, shock)"),
    "Crescendo": _m("Offense", 1, (3, 3, 4), "+20% DAMAGE to stunned titans"),
    "Blitzblade": _m("Offense", 1, (0, 0, 5), "Holding M1 increases your damage"),
    "Swiftshot": _m("Offense", 1, (0, 4, 3), "Refills 25% faster"),
    "Surgeshot": _m("Offense", 1, (0, 4, 0), "Holding a spear's M1 grows the blast radius"),
    "Stalwart": _m("Offense", 2, (0, 0, 2), "Blade durability +3% per broken segment"),
    "Stormcharged": _m("Offense", 2, (3, 3, 3), "+3% DAMAGE per shifter in the match"),
    "Quakestrike": _m("Offense", 3, (15, 12, 18), "+1.5% DAMAGE per kill until you reload / shift (20 kills shifted, 50 human)"),
    "Furyforge": _m("Offense", 3, (6, 6, 6), "+0.4% DAMAGE per 1% health lost"),
    "Assassin": _m("Offense", 3, (0, 0, 10), "Blade skills +25% DAMAGE and 15% shorter cooldowns"),
    "Amputation": _m("Offense", 3, (2, 4, 6), "Crits on limbs stop them regenerating"),
    "Supernova": _m("Offense", 3, (0, 14, 0), "+25% DAMAGE, -2.5% per 100m from the explosion"),
    "Marksman": _m("Offense", 3, (0, 12, 0), "+0.4% DAMAGE per 5m a spear travels (up to 465m)"),
    "Overslash": _m("Offense", 4, (6, 8, 10), "30% of overkill damage hits up to 3 titans nearby"),
    "Gambler": _m("Offense", 4, (3, 3, 3), "All damage rolls 75%-130%"),
    "Afterimages": _m("Offense", 4, (0, 20, 0), "Spear explosions leave a second explosion (40% DAMAGE)"),
    "Sparks of Black": _m("Offense", 5, (12, 14, 16), "+20% super crit chance, +40% super crit damage"),
    "Shatterpoint": _m("Offense", 5, (10, 14, 18), "Hits on the same limb add up to +75% damage taken"),
    "Guardian": _m("Defense", 1, (2, 2, 2), "Ignore 2 injuries per match"),
    "Deflectra": _m("Defense", 1, (1, 1, 1), "5% chance to ignore an injury"),
    "Aegisurge": _m("Defense", 2, (1, 2, 3), "Shield after a kill"),
    "Riposte": _m("Defense", 2, (0, 0, 2), "Counters execute a titan"),
    "Resilience": _m("Defense", 3, (4, 4, 4), "Ignore 1 killing blow per match"),
    "Vengeflare": _m("Defense", 3, (1, 1, 1), "Reflect damage while Tough as Nails is up"),
    "Steel Frame": _m("Defense", 3, (0, 5, 0), "Explosions deal 25% less self damage"),
    "Necromantic": _m("Defense", 4, (3, 3, 3), "After ignoring death: +20% DAMAGE, +25% HP, +15% SPEED"),
    "Thanatophobia": _m("Defense", 4, (4, 4, 4), "Below 40% HP: +25% damage reduction, injuries heal"),
    "Living Legend": _m("Defense", 5, (8, 8, 8), "HEALTH x1.25, immune to injuries, stronger healing"),
    "Untouchable": _m("Defense", 5, (6, 8, 10), "+2% ALL stats per second untouched (10s); take 1.5x damage"),
    "Cooldown Blitz": _m("Support", 1, (5, 4, 4), "Skill cooldowns -10%"),
    "Mendmaster": _m("Support", 1, (0, 1, 1), "An extra bandage on every refill"),
    "Lifefeed": _m("Support", 2, (2, 2, 2), "Heal 2% per kill"),
    "Vitalize": _m("Support", 2, (1, 1, 1), "Saving a teammate heals and buffs you both"),
    "Gem Fiend": _m("Support", 2, (0, 0, 0), "+10% gems from the AFK zone / mission streak"),
    "Omnirange": _m("Support", 3, (0, 0, 0), "Ranged skills reach every player"),
    "Flashstep": _m("Support", 3, (0, 0, 6), "Flips and dashes have I-frames"),
    "Tactician": _m("Support", 3, (2, 2, 2), "Support skills +15% effect"),
    "Bloodthief": _m("Support", 4, (0, 2, 4), "Hooked on a titan: heal 3% every 2s"),
    "Apotheosis": _m("Support", 4, (10, 10, 4), "Awakening 15% faster, shift at 60%, +1.25% DAMAGE per 10% of bar",
                     {"shift60": 1, "awaken": 15}),
    "Overclocked": _m("Support", 5, (0, 4, 20), "Hooks deal damage; +3% ODM/TS damage and +6% speed per hook (15 stacks)"),
    "Divine Decree": _m("Support", 5, (2, 2, 2), "Orders and flares x1.4, all fire at once, +15% shield to allies"),
}

FAMILY_SLOTS = {  # extra perk slots a family gives (family slots can't hold Divine perks - except Shiki's Body slot)
    "Ackerman": ("Offense",), "Yeager": ("Defense",), "Reiss": ("Support",), "Fritz": ("Defense", "Support"),
    "Helos": ("Offense", "Support"), "Shiki": ("Body",),
}
FAMILIES = ("None of these",) + tuple(sorted(FAMILY_SLOTS))
MEMORY_SLOTS = 5

# =============================================================================
#  Stats: how each one adds up, how it reads, what it's worth per playstyle
# =============================================================================
# kind: sum (adds up), flag (have it or not), max (the best one counts), min (the lowest one counts)
STATS = {
    "shifter_dmg": ("sum", "+{v}% shifter damage", (1.0, 0.35, 0)),
    "titan_stats": ("sum", "+{v}% all titan stats", (0.7, 0.25, 0)),
    "titan_burst": ("sum", "+{v}% titan stats for 20s after shifting", (0.25, 0.08, 0)),
    "awaken": ("sum", "awakening bar {v}% faster", (0.25, 0.15, 0.02)),
    "shift60": ("flag", "shift at 60% awakening bar", (12, 8, 0)),
    "max_shifts": ("sum", "+{v} maximum shifts", (1.5, 0.8, 0)),
    "shifts_row": ("max", "shift up to {v}x in a row", (1.5, 0.8, 0)),
    "aggro": ("sum", "+{v}m aggro range", (0.02, 0.01, 0)),
    "shift_aoe": ("sum", "shifting deals {v}% damage around you", (0.2, 0.08, 0)),
    "fear3": ("flag", "every 3 titan hits inflict fear", (3, 1, 0)),
    "punch_speed": ("sum", "+{v}% punching speed", (0.3, 0.1, 0)),
    "m1_speed": ("sum", "+{v}% shifter M1 speed", (0.6, 0.2, 0)),
    "skill_cd": ("sum", "{v}% shorter skill cooldowns", (0.5, 0.4, 0.4)),
    "skill_dmg": ("sum", "+{v}% damage for 5s after a skill", (0.3, 0.2, 0.2)),
    "skills_off": ("flag", "disables all equipped skills", (-40, -40, -5)),
    "odm_dmg": ("sum", "+{v}% ODM/TS damage", (0, 1.0, 1.0)),
    "odm_ts_all": ("sum", "+{v}% all ODM/TS stats", (0, 0.8, 0.8)),
    "odm_all": ("sum", "+{v}% all ODM stats", (0, 0, 0.8)),
    "ts_all": ("sum", "+{v}% all TS stats", (0, 0.8, 0)),
    "crit_chance": ("sum", "+{v}% crit chance", (0, 0.35, 0.5)),
    "crit_dmg": ("sum", "+{v}% crit damage", (0, 0.2, 0.3)),
    "limbs_blade": ("sum", "blades hit +{v} limbs at once", (0, 0, 3)),
    "limbs_ts": ("sum", "spears hit +{v} limbs at once", (0, 4, 0)),
    "blade_dur": ("sum", "+{v}% blade durability", (0, 0, 0.08)),
    "conserve": ("sum", "+{v}% conserve chance", (0, 0.4, 0)),
    "swing": ("sum", "+{v}% swing duration", (0, 0, 0.2)),
    "spear_count": ("sum", "+{v} spears", (0, 3, 0)),
    "spear_speed": ("sum", "+{v}% spear speed", (0, 0.08, 0)),
    "blast": ("sum", "+{v}% blast radius", (0, 0.3, 0)),
    "no_recoil": ("flag", "no spear recoil", (0, 2, 0)),
    "burn": ("sum", "{v}% burn damage on hit", (0, 0.4, 0.4)),
    "bleed": ("sum", "{v}% bleed damage on hit", (0, 0.1, 0.4)),
    "corrosion": ("flag", "hits inflict corrosion", (0, 5, 0)),
    "hook_speed": ("sum", "+{v}% hook speed", (0, 0.05, 0.2)),
    "maxdmg_at": ("min", "max damage at {v}% of your top speed", (0, 0.05, 0.3)),
    "mobility": ("sum", "+{v}% ODM speed / control / gas / range", (0.03, 0.12, 0.25)),
    "hit_stacks": ("sum", "+{v}% damage from hit stacks", (0, 0.6, 0.6)),
    "kill_chance": ("sum", "{v}% chance to kill on injuring", (0, 0.6, 1.0)),
    "dash_iframes": ("flag", "dashes phase through titans", (0, 1, 3)),
    "dmg_eq": ("sum", "about +{v}% ODM/TS damage", (0, 0.9, 1.0)),
    "dmg_all": ("sum", "about +{v}% damage", (0.8, 0.8, 0.8)),
    "dr": ("sum", "+{v}% damage reduction", (0.35, 0.35, 0.35)),
    "health": ("sum", "+{v} health", (0.04, 0.04, 0.04)),
    "injury": ("sum", "{v}% less injury chance", (0.15, 0.15, 0.15)),
    "inj_ignore": ("sum", "injuries ignored: {v}", (1.0, 1.0, 1.0)),
    "regen": ("sum", "+{v} health regen", (0.5, 0.5, 0.5)),
    "grab_escape": ("flag", "easier grab escapes", (3, 3, 3)),
    "dodge": ("sum", "{v}% dodge chance", (0.3, 0.3, 0.3)),
    "kb_ignore": ("flag", "survives one killing blow", (6, 6, 6)),
    "dmg_taken": ("sum", "takes {v}% more damage", (-0.15, -0.15, -0.15)),
    "skill_power": ("sum", "skills deal +{v}% damage", (0.25, 0.2, 0.2)),
    "kill_dmg": ("sum", "+{v}% damage per kill (party)", (20, 20, 20)),
    "utility": ("sum", "utility", (0.5, 0.5, 0.5)),
    "orders": ("flag", "stronger orders and flares (party)", (0, 0, 0)),
    "cannon": ("sum", "+{v}% cannon damage", (0, 0, 0)),
}
STAT_KEYS = tuple(STATS)
COUNT_STATS = ("limbs_blade", "limbs_ts", "inj_ignore", "shifts_row", "max_shifts", "spear_count", "health", "aggro")
_IDX = {k: i for i, k in enumerate(STAT_KEYS)}

# The macro's rules (from the build pages): never-use only where the macro runs (Shifter, Thunder Spear).
_NEVER = {"perks": ("Adaptation", "Tatsujin", "Wings of Freedom"), "memories": ("Flashstep",)}
RULES = {
    "Shifter": {"memories": ("Blood Awakening",), "perks_any": (),
                "preferred": ("Warchief", "Stormwrath", "Immortal", "Founder's Blessing", "Avatar of Ymir"),
                "never": _NEVER},
    "Thunder Spear": {"memories": ("Apotheosis", "Afterimages"), "perks_any": ("Godforged", "Avatar of Ymir"),
                      "preferred": ("Kengo", "Godforged", "Immortal", "Founder's Blessing", "Avatar of Ymir",
                                    "Munitions Master"),
                      "never": _NEVER},
    "ODM": {"memories": (), "perks_any": (), "preferred": (), "never": {"perks": (), "memories": ()}},
}
PREFERRED_BONUS = 8.0  # points: a preferred perk wins close calls, never a clearly better one
MAX_LEVEL = 10


def value_at(v, level):
    """A stat at a perk level (+0..+10)."""
    if isinstance(v, tuple):
        lv = max(0, min(MAX_LEVEL, int(level)))
        return v[0] + (v[1] - v[0]) * lv / float(MAX_LEVEL)
    return float(v)


def fmt_num(x):
    return ("%d" % round(x)) if abs(x - round(x)) < 0.05 else ("%.1f" % x)


def perk_lines(name, level, limit=None, playstyle=None):
    """Readable stat lines of a perk at a level. With a playstyle: what matters most for it comes first."""
    items = []
    for key, v in PERKS[name]["stats"].items():
        if key in ("utility", "orders"):
            continue
        val = value_at(v, level)
        weight = 0.0
        if playstyle:
            w = STATS[key][2][PLAYSTYLES.index(playstyle)]
            weight = abs(w * ((100.0 - val) if key == "maxdmg_at" else val))
        shown = abs(val) if key == "dmg_taken" else val
        if key in COUNT_STATS:
            shown = int(round(shown))  # limbs, injuries, spears, shifts and health are whole numbers in the game
        items.append((weight, STATS[key][1].replace("{v}", fmt_num(shown))))
    if playstyle:
        items.sort(key=lambda t: -t[0])
    out = [t for _, t in items] or list(PERKS[name]["text"][:1])
    return out[:limit] if limit else out


# =============================================================================
#  Scoring
# =============================================================================
def _ps(playstyle):
    return PLAYSTYLES.index(playstyle)


def stat_totals(perks, memories=()):
    """perks: [(name, level)] -> {stat: total} (sum / flag / max / min as the stat says)."""
    tot = {}
    sources = [{k: value_at(v, lv) for k, v in PERKS[n]["stats"].items()} for n, lv in perks]
    sources += [MEMORIES[m]["stats"] for m in memories]
    for src in sources:
        for k, v in src.items():
            kind = STATS[k][0]
            if k not in tot:
                tot[k] = min(v, 1.0) if kind == "flag" else v
            elif kind == "sum":
                tot[k] += v
            elif kind == "flag":
                tot[k] = max(tot[k], min(v, 1.0))
            elif kind == "max":
                tot[k] = max(tot[k], v)
            elif kind == "min":
                tot[k] = min(tot[k], v)
    return tot


def score_totals(tot, playstyle):
    i = _ps(playstyle)
    s = 0.0
    for k, v in tot.items():
        w = STATS[k][2][i]
        if not w:
            continue
        s += w * ((100.0 - v) if k == "maxdmg_at" else v)
    return s


def score_build(perks, memories, playstyle):
    """Score of a whole build (perks: [(name, level)], memories: [name])."""
    i = _ps(playstyle)
    rules = RULES[playstyle]
    s = score_totals(stat_totals(perks, memories), playstyle)
    s += sum(MEMORIES[m]["points"][playstyle] for m in memories)
    s += PREFERRED_BONUS * sum(1 for n, _ in perks if n in rules["preferred"])
    return s


# =============================================================================
#  Slots and the solver
# =============================================================================
class Slot:
    def __init__(self, name, cats, divine, family=False):
        self.name, self.cats, self.divine, self.family = name, frozenset(cats), divine, family

    def fits(self, perk):
        p = PERKS[perk]
        return p["cat"] in self.cats and (self.divine or p["rarity"] != "Divine")

    def __repr__(self):
        return "Slot(%s)" % self.name


def make_slots(family="None of these", capstones=()):
    """Your perk slots: Body (any perk, Divine too), Offense / Defense / Support (Divine with that capstone), plus the
    family's extra slots (no Divine - Shiki's extra Body slot excepted)."""
    caps = set(capstones or ())
    slots = [Slot("Body", CATEGORIES, True)]
    for cat in ("Offense", "Defense", "Support"):
        slots.append(Slot(cat, (cat,), cat in caps))
    for extra in FAMILY_SLOTS.get(family, ()):
        if extra == "Body":
            slots.append(Slot("Body (%s)" % family, CATEGORIES, True, True))
        else:
            slots.append(Slot("%s (%s)" % (extra, family), (extra,), False, True))
    return slots


class Build:
    def __init__(self, playstyle, slots, chosen, memories, score):
        self.playstyle = playstyle
        self.slots = slots            # [Slot]
        self.chosen = chosen          # [(name, level) or None] per slot
        self.memories = memories      # [name]
        self.score = score

    def perks(self):
        return [c for c in self.chosen if c]


def _usable(playstyle, owned_perks):
    never = RULES[playstyle]["never"]["perks"]
    return {n: lv for n, lv in owned_perks.items() if n in PERKS and n not in never}


def _best_perks(playstyle, slots, owned, memories, keep=7):
    """The best perks for these slots (distinct perks, rules kept): branch and bound over each slot's best
    candidates. The bound (a perk's value on its own) never underestimates, because perks only overlap (flags,
    max/min stats) - they never boost each other."""
    rules = RULES[playstyle]
    base = score_build([], memories, playstyle)
    solo = {n: score_build([(n, lv)], memories, playstyle) - base for n, lv in owned.items()}
    cands = []
    for slot in slots:
        fit = [n for n in owned if slot.fits(n)]
        fit.sort(key=lambda n: (-solo[n], n))
        cands.append([n for n in fit if solo[n] > 0][:keep])
    best = {"score": None, "pick": None}

    def search(fixed):
        """Best pick with `fixed` ({slot index: perk}) in place."""
        free = sorted((i for i in range(len(slots)) if i not in fixed), key=lambda i: len(cands[i]))
        used0 = set(fixed.values())
        part0 = sum(solo[n] for n in fixed.values())
        remain = [0.0] * (len(free) + 1)
        for j in range(len(free) - 1, -1, -1):
            c = [n for n in cands[free[j]] if n not in used0]
            remain[j] = remain[j + 1] + (max(solo[n] for n in c) if c else 0.0)
        pick = [fixed.get(i) for i in range(len(slots))]

        def dfs(j, used, partial):
            if best["score"] is not None and base + partial + remain[j] <= best["score"] + 1e-9:
                return  # can't beat the best found (the bound never underestimates)
            if j == len(free):
                names = [n for n in pick if n]
                s = score_build([(n, owned[n]) for n in names], memories, playstyle)
                if best["score"] is None or s > best["score"] + 1e-9:
                    best["score"], best["pick"] = s, list(pick)
                return
            i = free[j]
            for n in cands[i]:
                if n in used:
                    continue
                pick[i] = n
                used.add(n)
                dfs(j + 1, used, partial + solo[n])
                used.discard(n)
                pick[i] = None
            dfs(j + 1, used, partial)

        dfs(0, set(used0), part0)

    must_any = [n for n in rules["perks_any"] if n in owned]
    placements = [(i, n) for n in must_any for i, s in enumerate(slots) if s.fits(n)]
    if placements:  # a must-have (one of them) goes in: try each one in each slot it fits
        for i, n in placements:
            search({i: n})
    else:
        search({})
    pick = best["pick"] or [None] * len(slots)
    return [(n, owned[n]) if n else None for n in pick]


def _best_memories(playstyle, perks, owned_mem, n_slots=MEMORY_SLOTS):
    rules = RULES[playstyle]
    usable = [m for m in owned_mem if m in MEMORIES and m not in rules["never"]["memories"]]
    chosen = [m for m in rules["memories"] if m in usable][:n_slots]
    while len(chosen) < n_slots:
        cur = score_build(perks, chosen, playstyle)
        gains = [(score_build(perks, chosen + [m], playstyle) - cur, m) for m in usable if m not in chosen]
        gains = [g for g in gains if g[0] > 0]
        if not gains:
            break
        chosen.append(max(gains)[1])
    return chosen


def best_build(playstyle, owned_perks, owned_memories, family="None of these", capstones=()):
    """The best build you can equip. owned_perks: {name: level}, owned_memories: iterable of names."""
    slots = make_slots(family, capstones)
    owned = _usable(playstyle, owned_perks)
    memories = _best_memories(playstyle, [], owned_memories)
    chosen = _best_perks(playstyle, slots, owned, memories)
    for _ in range(3):  # perks and memories affect each other a little (shift at 60%): settle both
        mem2 = _best_memories(playstyle, [c for c in chosen if c], owned_memories)
        if mem2 == memories:
            break
        memories = mem2
        chosen = _best_perks(playstyle, slots, owned, memories)
    perks = [c for c in chosen if c]
    return Build(playstyle, slots, chosen, memories, score_build(perks, memories, playstyle))


def ideal_owned():
    return {n: MAX_LEVEL for n in PERKS}, set(MEMORIES)


# =============================================================================
#  Why, and what to get next
# =============================================================================
def missing_rules(build, owned_perks, owned_memories):
    """Required things the build doesn't have: [(kind, names)]."""
    rules = RULES[build.playstyle]
    out = []
    for m in rules["memories"]:
        if m not in owned_memories:
            out.append(("memory", (m,)))
    if rules["perks_any"] and not any(n in owned_perks for n in rules["perks_any"]):
        out.append(("perk", tuple(rules["perks_any"])))
    return out


def how_to_get(name, kind):
    if kind == "memory":
        return "roll it with prestige scrolls"
    if kind == "capstone":
        return "skill tree capstone"
    if PERKS[name]["rarity"] == "Divine":
        return "craft from divine fragments (Freedom difficulty)"
    return "drops from missions and raids"


def _perk_where(name, capstones):
    """Which slot a perk would go in, in words (Divine perks need the matching capstone outside the Body slot)."""
    p = PERKS[name]
    if p["cat"] == "Core":
        return "Body slot"
    if p["rarity"] == "Divine" and p["cat"] not in (capstones or ()):
        return "Body slot (or %s with the %s capstone)" % (p["cat"], p["cat"])
    return "%s slot" % p["cat"]


def get_next(build, owned_perks, owned_memories, family="None of these", capstones=(), limit=3, rarities=None):
    """The biggest upgrades you don't have yet: [{title, detail, gain (% of the build's score), kind, name}].
    rarities: only suggest new perks of these (perks of rarities you don't scan may already be yours)."""
    ps = build.playstyle
    base = max(build.score, 1e-6)
    recs = []
    for kind, names in missing_rules(build, owned_perks, owned_memories):
        what = " or ".join(names) + (" memory" if kind == "memory" else "")
        recs.append({"title": what, "kind": kind, "name": names[0], "gain": None, "required": True,
                     "detail": "required for %s - %s" % (ps, how_to_get(names[0], kind))})
    never = RULES[ps]["never"]
    slots = build.slots
    equipped = {n for n, _ in build.perks()}
    # perks: new ones at +10, or ones you own levelled to +10
    weakest = {}
    for slot, c in zip(slots, build.chosen):
        v = 0.0 if not c else score_build([c], build.memories, ps) - score_build([], build.memories, ps)
        weakest[slot.name] = v
    for n, p in PERKS.items():
        if n in never["perks"] or any(r["name"] == n for r in recs):
            continue
        lv = owned_perks.get(n)
        if lv is not None and lv >= MAX_LEVEL:
            continue
        if lv is None and rarities is not None and p["rarity"] not in rarities:
            continue
        fit = [s for s in slots if s.fits(n)]
        if not fit:
            continue
        solo = score_build([(n, MAX_LEVEL)], build.memories, ps) - score_build([], build.memories, ps)
        if solo <= min(weakest[s.name] for s in fit) and n not in equipped:
            continue  # even at +10 it can't beat anything it could replace
        trial = dict(owned_perks)
        trial[n] = MAX_LEVEL
        nb = best_build(ps, trial, owned_memories, family, capstones)
        gain = (nb.score - build.score) / base * 100.0
        if gain < 0.5:
            continue
        if lv is None:
            recs.append({"title": n, "kind": "perk", "name": n, "gain": gain, "required": False,
                         "detail": "%s - %s - %s" % (p["rarity"], _perk_where(n, capstones), how_to_get(n, "perk"))})
        else:
            recs.append({"title": "Level %s to +10" % n, "kind": "level", "name": n, "gain": gain, "required": False,
                         "detail": "you have it at +%d - enhance it" % lv if n in equipped else
                         "you have it at +%d - enhanced, it beats what you use now" % lv})
    # memories you don't have
    for m in MEMORIES:
        if m in owned_memories or m in never["memories"] or any(r["name"] == m for r in recs):
            continue
        nb = best_build(ps, owned_perks, set(owned_memories) | {m}, family, capstones)
        gain = (nb.score - build.score) / base * 100.0
        if gain >= 0.5:
            recs.append({"title": "%s memory" % m, "kind": "memory", "name": m, "gain": gain, "required": False,
                         "detail": "%d-star memory - %s" % (MEMORIES[m]["stars"], how_to_get(m, "memory"))})
    # capstones you haven't unlocked (only worth it with Divine perks you own)
    for cat in ("Offense", "Defense", "Support"):
        if cat in (capstones or ()):
            continue
        nb = best_build(ps, owned_perks, owned_memories, family, tuple(capstones or ()) + (cat,))
        gain = (nb.score - build.score) / base * 100.0
        if gain >= 0.5:
            div = [n for n, _ in nb.perks() if PERKS[n]["rarity"] == "Divine" and PERKS[n]["cat"] == cat]
            recs.append({"title": "Unlock the %s capstone" % cat, "kind": "capstone", "name": cat, "gain": gain,
                         "required": False,
                         "detail": "lets %s go in your %s slot" % (" and ".join(div) or "a Divine perk", cat)})
    req = [r for r in recs if r["required"]]
    rest = sorted((r for r in recs if not r["required"]), key=lambda r: -r["gain"])
    return (req + rest)[:limit]


def reasons(build, owned_perks):
    """Short plain reasons for the build: [text]."""
    ps = build.playstyle
    out = []
    rules = RULES[ps]
    base_mem = build.memories
    for slot, c in zip(build.slots, build.chosen):
        if not c:
            continue
        n, lv = c
        alts = [a for a in owned_perks if a != n and slot.fits(a) and a not in rules["never"]["perks"]
                and a not in [x[0] for x in build.perks()]]
        if alts:
            sa = {a: score_build([(a, owned_perks[a])], base_mem, ps) for a in alts}
            runner = max(sa, key=sa.get)
            out.append("%s in %s over %s: %s." % (n, slot.name, runner, perk_lines(n, lv, 1, ps)[0]))
    left = [n for n in owned_perks if n in rules["never"]["perks"]]
    if left:
        out.append("Left out by the macro's rules: %s." % ", ".join(left))
    divine_stuck = [n for n in owned_perks if n in PERKS and PERKS[n]["rarity"] == "Divine"
                    and PERKS[n]["cat"] != "Core" and n not in [x[0] for x in build.perks()]
                    and n not in rules["never"]["perks"]
                    and not any(s.fits(n) for s in build.slots if s.name != "Body")]
    if divine_stuck:
        out.append("%s can only go in the Body slot until you unlock the matching capstone." % ", ".join(divine_stuck))
    return out[:4]


# =============================================================================
#  Reading the game screen (Windows' built-in text recognition)
# =============================================================================
_FOLD = str.maketrans("0158|", "OISBI")  # what the text reader mixes up: 0/O, 1/I, 5/S, 8/B, |/I


def _norm(s, read=False):
    """A name reduced to letters, with look-alike characters folded together. read=True for text off the screen:
    the game writes names in capitals, so a small "l" there is a misread "I"."""
    if read:
        s = s.replace("l", "I")
    s = s.upper().replace("’", "'").replace("`", "'")
    return re.sub(r"[^A-Z0-9]", "", s).translate(_FOLD)


_PERK_NORM = {_norm(n): n for n in PERKS}
_MEM_NORM = {_norm(n): n for n in MEMORIES}


def match_name(text, table, cutoff=0.84):
    """The game name a piece of read text is (OCR slips allowed), or None."""
    t = _norm(text, read=True)
    if len(t) < 3:
        return None
    if t in table:
        return table[t]
    hit = difflib.get_close_matches(t, list(table), n=1, cutoff=cutoff)
    return table[hit[0]] if hit else None


def match_perk(text):
    return match_name(text, _PERK_NORM)


def match_memory(text):
    return match_name(text, _MEM_NORM, 0.86)


_LEVEL_RE = re.compile(r"^[+.,:*]?\s*(\d{1,2})$")


def parse_level(text):
    m = _LEVEL_RE.match(text.strip().replace(" ", ""))
    if not m:
        return None
    v = int(m.group(1))
    return v if 0 <= v <= MAX_LEVEL else None


def read_perk_panel(lines):
    """From OCR lines [(text, (x0, y0, x1, y1))] of the perk detail panel: (name, level) or (None, None).
    The name is the line that is a perk's name; the level is the "+N" box closest below it."""
    best = None
    for text, box in lines:
        n = match_perk(text)
        if n:
            h = box[3] - box[1]
            if best is None or h > best[2]:
                best = (n, box, h)
    if best is None:
        return None, None
    name, nbox, _ = best
    level = None
    cand = []
    for text, box in lines:
        lv = parse_level(text)
        if lv is not None and box[1] > nbox[1] and box[0] < nbox[2]:
            cand.append((box[1] - nbox[3], lv))
    if cand:
        level = min(cand)[1]
    return name, level


def _level_from_lines(lines):
    for text, _ in lines:
        t = text.strip().replace(" ", "")
        lv = parse_level(t)
        if lv is None:
            m = re.search(r"[+.,:*](\d{1,2})(?!\d)", t)  # "+7]" / "|+7" - the box's edge read as a letter
            if m and len(t) <= 6 and int(m.group(1)) <= MAX_LEVEL:
                lv = int(m.group(1))
        if lv is not None:
            return lv
    return None


_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%?\s*[x]?\s*~\s*(-?\d+(?:\.\d+)?)")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def level_from_stats(name, texts):
    """The perk's level worked out from the stat numbers the panel shows (they're the values at your level):
    (level, how many numbers agree) or (None, 0). Only ranges with a non-whole value somewhere in them count -
    whole-number stats (limbs, injuries, spears) are rounded in the game and can't tell levels apart."""
    ranges = []
    for t in PERKS[name]["text"]:
        for a, b in _RANGE.findall(t):
            a, b = float(a), float(b)
            if a != b and not (a.is_integer() and b.is_integer() and abs(b - a) <= 10):
                ranges.append((a, b))
    if not ranges:
        return None, 0
    nums = [float(x) for t in texts for x in _NUM.findall(t)]
    scores = []
    for lv in range(MAX_LEVEL + 1):
        exp = [a + (b - a) * lv / float(MAX_LEVEL) for a, b in ranges]
        hit = sum(1 for e in exp if any(abs(n - abs(e)) <= max(0.051, abs(e) * 0.004) for n in nums))
        scores.append((hit, lv))
    top = max(scores)
    if top[0] == 0 or sum(1 for s in scores if s[0] == top[0]) > 1:
        return None, 0
    return top[1], top[0]


def read_perk_panel_img(panel):
    """(name, level) from a picture of the perk detail panel. The level is the "+N" box under the name, checked
    against the stat numbers (they're shown at your level): a lone short number like "+7" is easy for the text
    reader to skip, and then the numbers decide; failing both, the strip under the name is read again, enlarged."""
    import cv2
    lines = ocr_lines(panel, 2.0)
    name, level = read_perk_panel(lines)
    if name is None:
        return None, None
    nbox = max((box for text, box in lines if match_perk(text) == name), key=lambda b: b[3] - b[1])
    if level is not None:
        return name, level
    stat_texts = [text for text, box in lines if box[1] > nbox[3] and parse_level(text) is None]
    st_level, st_hits = level_from_stats(name, stat_texts)
    if st_level is not None:
        return name, st_level
    nh = max(8, nbox[3] - nbox[1])
    below = [box[1] for text, box in lines if box[1] > nbox[3] + nh * 0.5 and match_perk(text) != name]
    y0 = int(nbox[3] + nh * 0.2)
    y1 = int(min(below)) if below else int(nbox[3] + nh * 6)
    y1 = min(panel.shape[0], max(y1, y0 + nh))
    x0 = max(0, int(nbox[0] - nh * 3))
    x1 = min(panel.shape[1], int(nbox[2]))
    strip = panel[y0:y1, x0:x1]
    if strip.size == 0:
        return name, None
    for scale in (3.0, 4.0):
        level = _level_from_lines(ocr_lines(strip, scale))
        if level is not None:
            return name, level
    # last try: bright text only, black on white
    g = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(g, 170, 255, cv2.THRESH_BINARY_INV)
    pad = cv2.copyMakeBorder(cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR), 20, 20, 20, 20, cv2.BORDER_CONSTANT,
                             value=(255, 255, 255))
    return name, _level_from_lines(ocr_lines(pad, 3.0))


def read_memories(lines):
    """Memory names on a screen (the Prestige page or the memory storage)."""
    out = []
    for text, _ in lines:
        m = match_memory(text)
        if m and m not in out:
            out.append(m)
    return out


try:  # Windows' text recognition (Windows 10+); the scan is off without it
    import asyncio
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
    _OCR_IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover
    OcrEngine = None
    _OCR_IMPORT_ERROR = _e

_ENGINE = []


def ocr_available():
    if OcrEngine is None:
        return False
    if not _ENGINE:
        try:
            _ENGINE.append(OcrEngine.try_create_from_user_profile_languages())
        except Exception:
            _ENGINE.append(None)
    return _ENGINE[0] is not None


def ocr_lines(img_bgr, scale=2.0):
    """[(text, (x0, y0, x1, y1))] of the text in a BGR image (boxes in the image's own pixels)."""
    import cv2
    if not ocr_available():
        raise RuntimeError("Windows text recognition isn't available on this PC")
    if scale != 1.0:
        img_bgr = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    h, w = bgra.shape[:2]
    dw = DataWriter()
    dw.write_bytes(bgra.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)

    async def run():
        return await _ENGINE[0].recognize_async(bmp)

    res = asyncio.run(run())
    out = []
    for line in res.lines:
        ws = list(line.words)
        if not ws:
            continue
        x0 = min(wd.bounding_rect.x for wd in ws) / scale
        y0 = min(wd.bounding_rect.y for wd in ws) / scale
        x1 = max(wd.bounding_rect.x + wd.bounding_rect.width for wd in ws) / scale
        y1 = max(wd.bounding_rect.y + wd.bounding_rect.height for wd in ws) / scale
        out.append((line.text, (int(x0), int(y0), int(x1), int(y1))))
    return out


def _square_boxes(mask, h):
    """Square-ish outlines of tile size in a mask whose border reaches the box corners (round tabs don't)."""
    import cv2
    cnts, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if not (h * 0.05 <= bw <= h * 0.17 and abs(bw - bh) <= 0.12 * bw):
            continue  # square (a tile cut off by the list's edge isn't)
        cw = max(3, int(bw * 0.12))
        corners = (mask[y:y + cw, x:x + cw], mask[y:y + cw, x + bw - cw:x + bw],
                   mask[y + bh - cw:y + bh, x:x + cw], mask[y + bh - cw:y + bh, x + bw - cw:x + bw])
        if sum(1 for k in corners if k.size and k.any()) >= 2:
            boxes.append((x, y, bw, bh))
    return boxes


def _tile_like(edges, cx, cy, size):
    """Does the grid cell at (cx, cy) hold a tile - a square outline of any colour (grey Common borders too)?"""
    hh, ww = edges.shape[:2]
    half = size / 2.0
    x0, y0, x1, y1 = int(round(cx - half)), int(round(cy - half)), int(round(cx + half)), int(round(cy + half))
    if x0 < 0 or y0 < 0 or x1 > ww or y1 > hh or x1 - x0 < 8 or y1 - y0 < 8:
        return False  # not fully on screen (a tile cut off by the list's edge isn't clicked yet)
    cell = edges[y0:y1, x0:x1]
    b = max(3, int(size * 0.14))
    sides = (cell[:b, :].any(axis=0).mean(), cell[-b:, :].any(axis=0).mean(),
             cell[:, :b].any(axis=1).mean(), cell[:, -b:].any(axis=1).mean())
    return sum(1 for v in sides if v >= 0.6) == 4  # all four edges: a tile cut off by the list's edge waits


def find_perk_grid(img_bgr, geom=None):
    """The perk tiles on the Perks screen (left part).
    Returns {"cells": [(cx, cy)] row by row - only cells that hold a tile, "size", "tabs": [(cx, cy)] the category
    tabs above the grid (empty when there are none), "bottom", "cols", "rows", "geom"} or None.
    Without `geom` the grid's shape (columns, tile size, row spacing, where the list starts) comes from the tiles'
    coloured borders; pass the first page's "geom" back in on later pages: then the rows are found by looking for
    tile outlines of any colour along those columns (a page of grey Common tiles has no colour to find)."""
    import cv2
    import numpy as np
    h, w = img_bgr.shape[:2]
    roi = img_bgr[:, : int(w * 0.45)]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((3, 3), np.uint8))
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 110)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    boxes = _square_boxes(mask, h)
    if geom is None and len(boxes) < 3:
        boxes = _square_boxes(edges, h)  # no coloured tiles: try plain outlines
    if geom is None:
        if len(boxes) < 3:
            return None
        size = float(np.median([b[2] for b in boxes]))
    else:
        size = geom["size"]
    boxes = [b for b in boxes if abs(b[2] - size) < 0.15 * size]
    uniq = []
    for b in sorted(boxes, key=lambda b: -b[2]):
        if all(abs(b[0] - o[0]) > size * 0.5 or abs(b[1] - o[1]) > size * 0.5 for o in uniq):
            uniq.append(b)
    centers = [(b[0] + b[2] / 2.0, b[1] + b[3] / 2.0) for b in uniq]

    def cluster(vals):
        vals = sorted(vals)
        groups = [[vals[0]]]
        for v in vals[1:]:
            if v - groups[-1][-1] <= size * 0.35:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [float(np.mean(g)) for g in groups]

    if geom is None:
        if len(uniq) < 3:
            return None
        cols = cluster([c[0] for c in centers])
        rows = cluster([c[1] for c in centers])
        pitch_x = float(np.median(np.diff(cols))) if len(cols) > 1 else size * 1.24
        pitch_y = float(np.median(np.diff(rows))) if len(rows) > 1 else pitch_x
        if not (size * 1.0 <= pitch_x <= size * 1.8 and size * 1.0 <= pitch_y <= size * 1.8):
            return None
        ncols = int(round((cols[-1] - cols[0]) / pitch_x)) + 1
        xs = [cols[0] + i * pitch_x for i in range(ncols)]
        top = rows[0] - size / 2.0 - size * 0.25  # where the list starts (it doesn't move while scrolling)
        phase = rows[0]
    else:
        xs, pitch_y, top = geom["xs"], geom["pitch_y"], geom["top"]
        near = [cy for cx, cy in centers if min(abs(cx - x) for x in xs) < size * 0.3]
        if near:
            phase = sorted(near)[len(near) // 2]  # any coloured tile's centre is on a row
        else:  # no coloured tile on this page: find where the rows are from the outlines
            best = (0, None)
            for off in range(0, int(pitch_y), 2):
                y = top + size / 2.0 + off
                n = 0
                while y + size / 2.0 <= h:
                    n += sum(1 for x in xs if _tile_like(edges, x, y, size))
                    y += pitch_y
                if n > best[0]:
                    best = (n, top + size / 2.0 + off)
            if best[1] is None:
                return None
            phase = best[1]
    # every row from the top of the list down; a row counts when one of its cells holds a tile
    y = phase
    while y - pitch_y - size / 2.0 >= top - size * 0.3:
        y -= pitch_y
    cells, ys = [], []
    while y + size / 2.0 <= h:
        row = []
        for x in xs:
            # clicked only where a whole tile outline is: colour only finds the grid's shape (coloured buttons
            # next to a half-hidden tile can look like a coloured square)
            if _tile_like(edges, x, y, size):
                row.append((int(round(x)), int(round(y))))
        if row:
            cells.extend(row)
            ys.append(y)
        elif ys:
            break  # the first empty row after tiles: the end of what's on screen
        y += pitch_y
    if not cells:
        return None
    # category tabs: the round icons just above the grid (one per category; a single icon = one category only)
    tabs = []
    if geom is None:
        y0, y1 = int(max(0, top - 2.0 * size)), int(max(0, top + size * 0.15))
        if y1 - y0 > size * 0.8:
            strip = cv2.medianBlur(cv2.cvtColor(img_bgr[y0:y1, : int(w * 0.45)], cv2.COLOR_BGR2GRAY), 3)
            circles = cv2.HoughCircles(strip, cv2.HOUGH_GRADIENT, dp=1.2, minDist=size * 0.8, param1=120, param2=22,
                                       minRadius=int(size * 0.3), maxRadius=int(size * 0.65))
            if circles is not None:
                found = sorted((int(x), int(y_) + y0) for x, y_, _ in circles[0])
                row_y = float(np.median([y_ for _, y_ in found]))
                found = [(x, y_) for x, y_ in found if abs(y_ - row_y) < size * 0.3]
                # real category tabs sit right over the grid's columns, one per column: anything else (round icons
                # elsewhere) isn't clicked - then only the list on screen is read
                cols_hit = {}
                for x, y_ in found:
                    k = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
                    if abs(xs[k] - x) <= size * 0.35 and k not in cols_hit:
                        cols_hit[k] = (x, y_)
                if len(cols_hit) >= 3 and len(cols_hit) == len(found):
                    tabs = [cols_hit[k] for k in sorted(cols_hit)]
    return {"cells": cells, "size": size, "tabs": tabs, "bottom": int(ys[-1] + size / 2.0), "cols": len(xs),
            "rows": len(ys), "geom": {"xs": xs, "size": size, "pitch_y": pitch_y, "top": top}}
