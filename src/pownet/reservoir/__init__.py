""" This is the reservoir module.
"""

<<<<<<< HEAD
from .reservoir import Reservoir, Basin, ReservoirOperator
from .solve_release import solve_release_from_storage, solve_release_from_dispatch
=======
from .reservoir import Reservoir
from .basin import Basin
from .reservoir_operator import ReservoirOperator
from .solve_release import (
    solve_release_from_target_storage,
    solve_release_from_dispatch,
)
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
