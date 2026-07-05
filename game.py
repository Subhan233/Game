import random

COMMENTARY_RUNS = {
    1: ["🏃 Quick single taken.", "1 run, good running."],
    2: ["🏃‍♂️🏃 Two runs, well placed.", "Good running between the wickets, 2 runs."],
    3: ["🏃 Three runs! Excellent placement.", "Fielder chases hard, 3 runs taken."],
    4: ["🔥 FOUR! Cracking shot to the boundary!", "💥 Boundary! That's a beauty!"],
    5: ["Rare 5! Overthrow helps the batter.", "5 runs! Brilliant running plus an extra."],
    6: ["🚀 SIX! That's out of the stadium!", "💥💥 MASSIVE SIX! Into the crowd!"],
}
COMMENTARY_WICKET = [
    "🎯 OUT! Clean bowled!",
    "☠️ Wicket! Great delivery!",
    "🔥 Gone! That's the breakthrough!",
    "🧤 Caught! Superb take!",
]


class InningsState:
    """Tracks one innings of a match (either the bot vs AI, or one side of a PvP match)."""

    def __init__(self, overs_limit: int, target: int | None = None, max_wickets: int = 2):
        self.overs_limit = overs_limit
        self.balls_bowled = 0
        self.wickets = 0
        self.score = 0
        self.target = target
        self.streak = 0  # consecutive boundaries (4s/6s)
        self.max_wickets = max_wickets
        self.bowler_wicket_streak = 0  # consecutive wickets taken while bowling
        self.hattrick_achieved = False
        self.log = []

    @property
    def overs_display(self):
        return f"{self.balls_bowled // 6}.{self.balls_bowled % 6}"

    @property
    def balls_left(self):
        return self.overs_limit * 6 - self.balls_bowled

    @property
    def is_powerplay(self):
        pp_balls = min(12, self.overs_limit * 6)
        return self.balls_bowled < pp_balls

    @property
    def is_over(self):
        if self.balls_left <= 0:
            return True
        if self.wickets >= self.max_wickets:
            return True
        if self.target is not None and self.score > self.target:
            return True
        return False


def ai_pick(difficulty: str, opponent_pick: int) -> int:
    """AI picks a number 1-6. Higher difficulty = more likely to match opponent's pick
    (i.e. take a wicket when bowling, or get out when batting)."""
    match_chance = {"easy": 0.12, "medium": 0.20, "hard": 0.30}.get(difficulty, 0.18)
    if random.random() < match_chance:
        return opponent_pick
    choices = [n for n in range(1, 7) if n != opponent_pick]
    return random.choice(choices)


def resolve_ball(batter_pick: int, bowler_pick: int, innings: InningsState):
    """Resolves one ball. Returns dict with event, commentary text, and runs scored."""
    innings.balls_bowled += 1

    if batter_pick == bowler_pick:
        innings.wickets += 1
        innings.streak = 0
        innings.bowler_wicket_streak += 1
        commentary = random.choice(COMMENTARY_WICKET)
        hattrick = False
        if innings.bowler_wicket_streak >= 3 and not innings.hattrick_achieved:
            hattrick = True
            innings.hattrick_achieved = True
            commentary += " 🎩🎩🎩 HAT-TRICK!"
        return {"event": "WICKET", "text": commentary, "runs": 0, "hattrick": hattrick}

    innings.bowler_wicket_streak = 0
    runs = batter_pick
    bonus = 0
    line = random.choice(COMMENTARY_RUNS[runs])

    if runs >= 4:
        innings.streak += 1
        if innings.streak >= 2:
            bonus += 2
            line += " 🔥 Streak bonus +2!"
    else:
        innings.streak = 0

    if innings.is_powerplay:
        bonus += runs
        line += " ⚡ Powerplay: runs doubled!"

    total_runs = runs + bonus
    innings.score += total_runs
    return {"event": "RUNS", "text": line, "runs": total_runs, "hattrick": False}
