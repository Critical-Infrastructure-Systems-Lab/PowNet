""" This script experiments with the reservoir module.
"""

from pownet.reservoir import Reservoir, Basin, ReservoirOperator


def main():
    model_name = "dummy_hydro"
    reservoir_name = "kirirom1"

    reservoir = Reservoir(model_name=model_name, reservoir_name=reservoir_name)
    reservoir.load_from_csv()
    reservoir.simulate()
    # reservoir.plot_state()
    reservoir.get_hourly_hydropower()

    basin = Basin(model_name=model_name, basin_name="mekong1")
    basin.load_csv()
    basin.simulate()
    basin.get_basin_hydropower(timestep="hourly")

    reservoir_operator = ReservoirOperator(model_name=model_name)
    reservoir_operator.load_csv()
    reservoir_operator.simulate()
    reservoir_operator.get_hourly_hydropower()


if __name__ == "__main__":
    main()
