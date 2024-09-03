from __future__ import annotations

import os

import pandas as pd
import matplotlib.pyplot as plt

from pownet.folder_utils import get_output_dir, get_database_dir


def get_fuel_color_map() -> dict:
    """Return a map of fuel type to its color. This is defined in the database folder."""
    fuel_color_map = (
        pd.read_csv(
            os.path.join(get_database_dir(), "fuels.csv"),
            header=0,
            usecols=["name", "color"],
        )
        .set_index("name")
        .to_dict()["color"]
    )
    return fuel_color_map


class Visualizer:
    def __init__(self, model_id: str) -> None:
        self.model_id: str = model_id
        self.fuel_color_map: dict = get_fuel_color_map()

    def plot_fuelmix_bar(
        self,
        dispatch: pd.DataFrame,
        demand: pd.Series,
        to_save: bool,
    ) -> None:
        """Create a bar plot of the fuel mix.

        Args:
            dispatch (pd.DataFrame): The dispatch of each generator.
            demand (pd.Series): The demand of the system.
            to_save (bool): Whether to save to the output directory.

        Returns:
            None
        """
        # Use total_timesteps to index demand because
        # the length of demand can be longer than the total simulation hours
        total_timesteps: int = dispatch.shape[0]
        # Plotting section
        fig, ax = plt.subplots(figsize=(8, 5))

        dispatch.plot.bar(
            stacked=True, ax=ax, linewidth=0, color=self.fuel_color_map, legend=False
        )
        ax.plot(
            range(0, total_timesteps),
            demand[:total_timesteps],
            color="k",
            linewidth=2,
            linestyle=":",
            label="demand",
        )
        ax.set_xlabel(dispatch.index.name)

        # Plot formatting
        legend = fig.legend(
            loc="outside lower center",
            ncols=4,
            fontsize="small",
            bbox_to_anchor=(0.5, -0.1),
        )
        ax.set_ylabel("Power (MW)")
        ax.set_ylim(bottom=0)

        if to_save:
            figure_name = f"{self.model_id}_fuelmix.png"
            fig.savefig(
                os.path.join(get_output_dir(), figure_name),
                bbox_extra_artists=(legend,),
                bbox_inches="tight",
                dpi=350,
            )

        plt.show()

    def plot_fuelmix_area(
        self,
        dispatch: pd.DataFrame,
        demand: pd.Series,
        to_save: bool,
    ) -> None:
        """Create an area plot of the fuel mix.

        Args:
            dispatch (pd.DataFrame): The dispatch of each generator.
            demand (pd.Series): The demand of the system.
            to_save (bool): Whether to save to the output directory.

        Returns:
            None

        """
        # Use total_timesteps to index demand because
        # the length of demand can be longer than the total simulation hours
        total_timesteps: int = dispatch.shape[0]

        fig, ax = plt.subplots(figsize=(8, 5))
        dispatch.plot.area(
            stacked=True, ax=ax, linewidth=0, color=self.fuel_color_map, legend=False
        )
        ax.plot(
            demand[:total_timesteps],
            color="k",
            linewidth=2,
            linestyle=":",
            label="demand",
        )
        ax.set_xlabel(dispatch.index.name)

        legend = fig.legend(
            loc="outside lower center",
            ncols=4,
            fontsize="small",
            bbox_to_anchor=(0.5, -0.1),
        )
        ax.set_ylabel("Power (MW)")
        ax.set_ylim(bottom=0)

        if to_save:
            figure_name = f"{self.model_id}_fuelmix.png"
            fig.savefig(
                os.path.join(get_output_dir(), figure_name),
                bbox_extra_artists=(legend,),
                bbox_inches="tight",
                dpi=350,
            )

        plt.show()

    def plot_thermal_units(
        self,
        thermal_dispatch: pd.DataFrame,
        unit_status: pd.DataFrame,
        thermal_rated_capacity: dict[str, float],
        to_save: bool,
    ) -> None:
        """Plot the on/off status of individual thermal units

        Args:
            thermal_dispatch (pd.DataFrame): The dispatch of each thermal unit.
            unit_status (pd.DataFrame): The status of each thermal unit.
            thermal_rated_capacity (dict[str, float]): Rated capacity of each thermal unit.
            to_save (bool): Whether to save to the output directory.

        Returns:
            None

        """
        thermal_units = thermal_dispatch["node"].unique()

        for unit_g in thermal_units:
            # Extract the dispatch of each thermal unit and plot the value
            df1 = thermal_dispatch[thermal_dispatch.node == unit_g]
            df2 = unit_status[unit_status["node"] == unit_g]

            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()

            ax1.step(df1["hour"], df1["value"], where="mid", color="b", label="Power")
            # If ymax is too low, then we cannot see the blue line
            ax1.set_ylim(bottom=0, top=thermal_rated_capacity[unit_g] * 1.05)
            ax1.tick_params(axis="x", labelrotation=45)
            ax1.set_xlabel("Hour")
            ax1.set_ylabel("Power (MW)")

            ax2.bar(
                df2["hour"], df2["value"], color="k", alpha=0.2, label="Unit status"
            )
            ax2.set_ylim(bottom=0, top=1)
            ax2.set_ylabel("Unit Status")
            plt.title(unit_g)

            if to_save:
                unit_plot_folder = os.path.join(
                    get_output_dir(), f"{self.model_id}_unit_plots"
                )
                if not os.path.exists(unit_plot_folder):
                    os.mkdir(unit_plot_folder)

                fig.savefig(
                    os.path.join(unit_plot_folder, f"{unit_g}.png"),
                    dpi=350,
                )

            plt.show()

    def plot_lmp(self, lmp_df: pd.DataFrame, to_save: bool) -> None:
        """Plots unique locational marginal price (LMP) timeseries.
        For each unique LMP timeseries, a representative node is chosen
        based on ordering in the dataframe.

        Args:
            lmp_df (pd.DataFrame): The locational marginal price.
            to_save (bool): Whether to save to the output directory.

        Returns:
            None

        """
        # Find uni
        unique_lmp = lmp_df.copy().T.drop_duplicates().T

        fig, ax = plt.subplots(figsize=(8, 5))
        unique_lmp.plot(ax=ax, linewidth=2)
        ax.set_xlabel("Hour")
        ax.set_ylabel("LMP ($/MWh)")
        # Place legend at the bottom
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4)

        if to_save:
            figure_name = f"{self.model_id}_lmp.png"
            fig.savefig(
                os.path.join(get_output_dir(), figure_name),
                dpi=350,
            )

        plt.show()
