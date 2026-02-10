import collections
import sys

from backend.game_logic import deal_roles


def run(trials: int = 300, players: int = 6) -> None:
    counts = collections.Counter()
    for _ in range(trials):
        spies, _, _ = deal_roles(list(range(players)), "standard")
        for spy in spies:
            counts[spy] += 1
    print(f"Trials: {trials}, Players: {players}")
    for player in range(players):
        print(player, counts[player])


if __name__ == "__main__":
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    players = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    run(trials, players)
