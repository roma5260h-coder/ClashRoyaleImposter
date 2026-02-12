import random
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, TypeVar

from data.cards import ALL_CARDS

T = TypeVar("T")


class PlayMode(str, Enum):
    STANDARD = "standard"
    RANDOM = "random"


class RandomScenario(str, Enum):
    STANDARD = "standard"
    ALL_SPIES = "all_spies"
    SAME_CARD = "same_card"
    ONE_OUTLIER_CARD = "one_outlier_card"
    DIFFERENT_CARDS = "different_cards"
    MULTIPLE_SPIES = "multiple_spies"


def _multiple_spies_count(player_count: int) -> int:
    if player_count <= 3:
        return 1
    if player_count == 4:
        return 2
    if player_count in (5, 6):
        return 2
    if player_count in (7, 8):
        return 3
    return 3


def _random_distinct_card(excluded_card: str) -> str:
    if len(ALL_CARDS) < 2:
        raise ValueError("Need at least 2 cards for outlier scenario")
    candidate = excluded_card
    while candidate == excluded_card:
        candidate = random.choice(ALL_CARDS)
    return candidate


def _resolve_random_scenario(player_count: int) -> RandomScenario:
    scenarios = [
        RandomScenario.STANDARD,
        RandomScenario.ALL_SPIES,
        RandomScenario.SAME_CARD,
        RandomScenario.ONE_OUTLIER_CARD,
        RandomScenario.DIFFERENT_CARDS,
    ]
    if player_count > 3:
        scenarios.append(RandomScenario.MULTIPLE_SPIES)
    return random.choice(scenarios)


def deal_roles(
    players: Sequence[T],
    play_mode: str
) -> Tuple[List[T], Dict[T, Optional[str]], Optional[str]]:
    player_list = list(players)
    if not player_list:
        return [], {}, None

    if play_mode == PlayMode.STANDARD.value:
        spy = random.choice(player_list)
        card = random.choice(ALL_CARDS)
        cards_for_players = {
            p: (None if p == spy else card) for p in player_list
        }
        return [spy], cards_for_players, None

    scenario = _resolve_random_scenario(len(player_list))

    if scenario == RandomScenario.STANDARD:
        spy = random.choice(player_list)
        card = random.choice(ALL_CARDS)
        cards_for_players = {
            p: (None if p == spy else card) for p in player_list
        }
        return [spy], cards_for_players, scenario.value

    if scenario == RandomScenario.ALL_SPIES:
        cards_for_players = {p: None for p in player_list}
        return list(player_list), cards_for_players, scenario.value

    if scenario == RandomScenario.SAME_CARD:
        card = random.choice(ALL_CARDS)
        cards_for_players = {p: card for p in player_list}
        return [], cards_for_players, scenario.value

    if scenario == RandomScenario.ONE_OUTLIER_CARD:
        base_card = random.choice(ALL_CARDS)
        outlier_card = _random_distinct_card(base_card)
        outlier_player = random.choice(player_list)
        cards_for_players = {
            p: (outlier_card if p == outlier_player else base_card) for p in player_list
        }
        return [], cards_for_players, scenario.value

    if scenario == RandomScenario.DIFFERENT_CARDS:
        cards_for_players = {p: random.choice(ALL_CARDS) for p in player_list}
        return [], cards_for_players, scenario.value

    spy_count = _multiple_spies_count(len(player_list))
    spies = random.sample(player_list, spy_count)
    card = random.choice(ALL_CARDS)
    cards_for_players = {
        p: (None if p in spies else card) for p in player_list
    }
    return spies, cards_for_players, scenario.value
