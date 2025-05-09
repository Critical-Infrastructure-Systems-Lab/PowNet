class ReservoirParams:
    """Class to hold reservoir parameters."""

    def __init__(self, name: str, cascade_level: int) -> None:
        self.name = name
        self.cascade_level = cascade_level
        self.inflow = None
        self.release = None
