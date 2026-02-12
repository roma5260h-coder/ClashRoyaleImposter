import secrets
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, TypeVar

from .data.cards import ALL_CARDS

T = TypeVar("T")


class GameMode(str, Enum):
    STANDARD = "standard"
    RANDOM = "random"


class RandomScenario(str, Enum):
    STANDARD = "standard"
    ALL_SPIES = "all_spies"
    SAME_CARD = "same_card"
    ONE_OUTLIER_CARD = "one_outlier_card"
    DIFFERENT_CARDS = "different_cards"
    MULTI_SPY = "multi_spy"


def multiple_spies_count(player_count: int) -> int:
    if player_count <= 3:
        return 1
    if player_count == 4:
        return 2
    if player_count in (5, 6):
        return 2
    if player_count in (7, 8):
        return 3
    return 3


_rng = secrets.SystemRandom()


def _random_distinct_card(excluded_card: str) -> str:
    """Return a random card name that is different from excluded_card."""
    if len(ALL_CARDS) < 2:
        raise ValueError("Need at least 2 cards for outlier scenario")

    candidate = excluded_card
    while candidate == excluded_card:
        candidate = _rng.choice(ALL_CARDS)
    return candidate


def resolve_random_scenario(
    player_count: int,
    allowed_scenarios: Optional[Sequence[str]] = None,
) -> RandomScenario:
    allowed_map = {scenario.value: scenario for scenario in RandomScenario}
    selected: List[RandomScenario] = []

    if allowed_scenarios:
        for value in allowed_scenarios:
            scenario = allowed_map.get(value)
            if scenario and scenario not in selected:
                selected.append(scenario)

    if not selected:
        selected = list(RandomScenario)

    if player_count <= 3 and RandomScenario.MULTI_SPY in selected:
        selected = [scenario for scenario in selected if scenario != RandomScenario.MULTI_SPY]
    if player_count < 2 and RandomScenario.ONE_OUTLIER_CARD in selected:
        selected = [scenario for scenario in selected if scenario != RandomScenario.ONE_OUTLIER_CARD]

    if not selected:
        raise ValueError("No valid random scenarios available")

    return _rng.choice(selected)


def deal_roles(
    players: Sequence[T],
    game_mode: str,
    random_allowed_modes: Optional[Sequence[str]] = None,
) -> Tuple[List[T], Dict[T, Optional[str]], Optional[str]]:
    player_list = list(players)
    if not player_list:
        return [], {}, None

    if game_mode == GameMode.STANDARD.value:
        spy = _rng.choice(player_list)
        card = _rng.choice(ALL_CARDS)
        cards_for_players = {
            p: (None if p == spy else card) for p in player_list
        }
        return [spy], cards_for_players, None

    scenario = resolve_random_scenario(len(player_list), random_allowed_modes)

    if scenario == RandomScenario.STANDARD:
        spy = _rng.choice(player_list)
        card = _rng.choice(ALL_CARDS)
        cards_for_players = {
            p: (None if p == spy else card) for p in player_list
        }
        return [spy], cards_for_players, scenario.value

    if scenario == RandomScenario.ALL_SPIES:
        cards_for_players = {p: None for p in player_list}
        return list(player_list), cards_for_players, scenario.value

    if scenario == RandomScenario.SAME_CARD:
        card = _rng.choice(ALL_CARDS)
        cards_for_players = {p: card for p in player_list}
        return [], cards_for_players, scenario.value

    if scenario == RandomScenario.ONE_OUTLIER_CARD:
        base_card = _rng.choice(ALL_CARDS)
        outlier_card = _random_distinct_card(base_card)
        outlier_player = _rng.choice(player_list)
        cards_for_players = {
            p: (outlier_card if p == outlier_player else base_card) for p in player_list
        }
        return [], cards_for_players, scenario.value

    if scenario == RandomScenario.DIFFERENT_CARDS:
        cards_for_players = {p: _rng.choice(ALL_CARDS) for p in player_list}
        return [], cards_for_players, scenario.value

    spy_count = multiple_spies_count(len(player_list))
    spies = _rng.sample(player_list, spy_count)
    card = _rng.choice(ALL_CARDS)
    cards_for_players = {
        p: (None if p in spies else card) for p in player_list
    }
    return spies, cards_for_players, scenario.value
