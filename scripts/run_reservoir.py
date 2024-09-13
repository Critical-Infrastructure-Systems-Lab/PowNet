""" This script experiments with the reservoir module.
"""

from pownet.reservoir import Reservoir


def main():
    model_name = "dummy_hydro"
    reservoir_name = "kirirom3"

    reservoir = Reservoir(model_name=model_name, reservoir_name=reservoir_name)
    reservoir.load_from_csv()
    reservoir.simulate()
    reservoir.plot_state()


if __name__ == "__main__":
    main()
