"""Disambiguate single/double A without changing mode on a double tap."""
class ATap:
    WINDOW = .35

    def __init__(self):
        self.pending = None
        self.cooldown = 0

    def reset(self):
        self.pending = None
        self.cooldown = 0

    def tick(self, now):
        if self.pending is not None and now-self.pending > self.WINDOW:
            self.pending = None
            return 'mode'

    def press(self, now):
        if now < self.cooldown:
            return None
        if self.pending is not None and now-self.pending <= self.WINDOW:
            self.pending = None
            self.cooldown = now+self.WINDOW
            return 'start'
        expired = self.pending is not None
        self.pending = now
        if expired: return 'mode'
