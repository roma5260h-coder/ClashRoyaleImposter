import random
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, TypeVar

from data.cards import ALL_CARDS

T = TypeVar("T")


class PlayMode(str, Enum):
    STANDARD = "standard"
    RANDOM = "random"


class RandomScenario(str, Enum):
    ALL_SPIES = "all_spies"
    SAME_CARD = "same_card"
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


def _resolve_random_scenario(player_count: int) -> RandomScenario:
    scenarios = [
        RandomScenario.ALL_SPIES,
        RandomScenario.SAME_CARD,
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

    if scenario == RandomScenario.ALL_SPIES:
        cards_for_players = {p: None for p in player_list}
        return list(player_list), cards_for_players, scenario.value

    if scenario == RandomScenario.SAME_CARD:
        card = random.choice(ALL_CARDS)
        cards_for_players = {p: card for p in player_list}
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
