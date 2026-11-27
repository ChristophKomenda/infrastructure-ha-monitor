"""Confirm diagnoses using independent snapshots."""


class Confirmation:

    def __init__(self, confirmations=2):
        self.confirmations = confirmations
        self.confirmed = ("unknown", "initializing")
        self.candidate = None
        self.count = 0
        self.last_pair = None

    def update(self, status, diagnosis, pair):
        current = (status, diagnosis)

        if status == "unknown":
            self.candidate = None
            self.count = 0
            self.confirmed = current
            return current

        fresh = (
            self.last_pair is None
            or all(
                new > old
                for new, old in zip(pair, self.last_pair)
            )
        )

        if not fresh:
            if (
                self.candidate is not None
                and current != self.candidate
            ):
                self.candidate = None
                self.count = 0

            if current != self.confirmed:
                return "unknown", "confirmation_pending"
            return self.confirmed

        self.last_pair = pair

        if current == self.confirmed:
            self.candidate = None
            self.count = 0
            return self.confirmed

        if current == self.candidate:
            self.count += 1
        else:
            self.candidate = current
            self.count = 1

        if self.count >= self.confirmations:
            self.confirmed = current
            self.candidate = None
            self.count = 0
            return current

        return "unknown", "confirmation_pending"
