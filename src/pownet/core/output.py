from datetime import datetime
import os

import pandas as pd
import matplotlib.pyplot as plt

from pownet.core.input import SystemInput
from pownet.folder_sys import get_output_dir, get_database_dir
from pownet.processing.functions import get_dates


def format_variable_fueltype(
    df: pd.DataFrame, vartype: str, fuel_type: str
) -> pd.DataFrame:
    """Given a dataframe of PowNet outputs, filter for a vartype and assign the fuel type.
    Use this function for import, s_pos, and s_neg.
    """
    output_df = df[df["vartype"] == vartype]
    output_df = output_df.reset_index(drop=True)
    output_df["fuel_type"] = fuel_type
    return output_df


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


class OutputProcessor:
    def __init__(self):
        self.model_name: str = None
        self.year: int = None

        self.total_timesteps: int = None  # Simulation hours
        self.ctime: str = None  # Date in 'YYYYMMDD_mmss' format
        self.dates: pd.Series = None

        self.fuelmap: dict[str, str] = None

        self.thermal_dispatch: pd.DataFrame = None
        self.rnw_dispatch: pd.DataFrame = None
        self.shortfall: pd.Series = None
        self.curtailment: pd.Series = None

        self.total_dispatch: pd.DataFrame = None
        self.monthly_dispatch: pd.DataFrame = None
        self.daily_dispatch: pd.DataFrame = None

        self.total_demand: pd.Series = None
        self.monthly_demand: pd.Series = None
        self.daily_demand: pd.Series = None

        # Define the order of fuel mix. Baseload at the bottom,
        # renewables in the middle, then peaker plants, and shortfall
        self.fuel_mix_order: list[str] = None

        self.unit_status: pd.DataFrame = None

    def load(
        self, df: pd.DataFrame, system_input: SystemInput, model_name: str
    ) -> None:
        """Process node-specific variables from PowNet."""
        self.model_name = model_name
        self.year = system_input.year

        # For saving files
        self.ctime = datetime.now().strftime("%Y%m%d_%H%M")

        # For processing dataframes
        self.dates = get_dates(year=self.year)
        self.dates.index += 1

        # -- Extract information from PowNet's node variables
        self.fuelmap = (
            system_input.fuelmap[["name", "fuel_type"]]
            .set_index("name")
            .to_dict()["fuel_type"]
        )

        # Generation from thermal units
        self.thermal_dispatch = df[df["vartype"] == "dispatch"]
        self.thermal_dispatch = self.thermal_dispatch
        self.thermal_dispatch = self.thermal_dispatch.reset_index(drop=True)
        self.thermal_dispatch["fuel_type"] = self.thermal_dispatch.apply(
            lambda x: self.fuelmap[x["node"]], axis=1
        )

        # Generation from renewables
        self.rnw_dispatch = df[df["vartype"] == "prnw"]
        # self.rnw_dispatch = self.rnw_dispatch.rename(columns={'value':'dispatch'})
        self.rnw_dispatch = self.rnw_dispatch.reset_index(drop=True)
        self.rnw_dispatch["fuel_type"] = self.rnw_dispatch.apply(
            lambda x: self.fuelmap[x["node"]], axis=1
        )

        # Generation from import nodes
        self.p_import = format_variable_fueltype(
            df=df, vartype="pimp", fuel_type="import"
        )
        # Shortfall (positive) and curtailment (negative)
        self.shortfall = format_variable_fueltype(
            df=df, vartype="s_pos", fuel_type="shortfall"
        )
        self.curtailment = format_variable_fueltype(
            df=df, vartype="s_neg", fuel_type="curtailment"
        )

        # Calculate the total dispatch for each fuel type and timestep
        self.total_dispatch = pd.concat(
            [
                self.thermal_dispatch,
                self.rnw_dispatch,
                self.p_import,
                self.shortfall,
                self.curtailment,
            ],
            axis=0,
        )
        self.total_dispatch = self.total_dispatch.reset_index(drop=True)
        self.total_dispatch = (
            self.total_dispatch[["fuel_type", "value", "hour"]]
            .groupby(["fuel_type", "hour"])
            .sum()
        )

        self.total_dispatch = self.total_dispatch.reset_index()
        self.total_dispatch = self.total_dispatch.pivot(
            columns=["hour"], index=["fuel_type"]
        ).T.reset_index(drop=True)
        # PowNet indexing starts at 1
        self.total_dispatch.index += 1

        # Reorder the columns of total dispatch in case we want to plot
        self.fuel_mix_order: pd.DataFrame = pd.read_csv(
            os.path.join(get_database_dir(), "fuels.csv"),
            header=0,
        )["name"]
        self.fuel_mix_order = [
            fuel for fuel in self.fuel_mix_order if fuel in self.total_dispatch.columns
        ]
        self.total_dispatch = self.total_dispatch[self.fuel_mix_order]

        # Sum across each month to get the monthly dispatch
        self.monthly_dispatch = self.total_dispatch.copy()
        self.monthly_dispatch["month"] = self.dates["date"].dt.to_period("M")
        self.monthly_dispatch = self.monthly_dispatch.groupby("month").sum()
        self.monthly_dispatch.index = self.monthly_dispatch.index.strftime("%b")

        # Sum across 24 hours to get the daily dispatch.
        self.daily_dispatch = self.total_dispatch.copy()
        self.daily_dispatch = self.daily_dispatch.groupby(
            self.daily_dispatch.index // 24
        ).mean()

        # Demand is an input to the simulation
        self.total_demand = system_input.demand.sum(axis=1)

        # Sum across each month to get the monthly demand
        self.monthly_demand = self.total_demand[: self.total_timesteps].to_frame()
        self.monthly_demand.columns = ["demand"]
        self.monthly_demand["month"] = self.dates["date"].dt.to_period("M")
        self.monthly_demand = self.monthly_demand.groupby("month").sum()
        self.monthly_demand.index = self.monthly_demand.index.strftime("%b")

        self.daily_demand = self.total_demand.groupby(
            self.total_demand.index // 24
        ).sum()

        # Need unit statuses for plotting their activities
        self.unit_status = df[df["vartype"] == "status"]

    def get_total_dispatch(self) -> pd.DataFrame:
        return self.total_dispatch

    def get_monthly_dispatch(self) -> pd.DataFrame:
        return self.monthly_dispatch

    def get_daily_dispatch(self) -> pd.DataFrame:
        return self.daily_dispatch

    def get_total_demand(self) -> pd.Series:
        return self.total_demand

    def get_monthly_demand(self) -> pd.Series:
        return self.monthly_demand

    def get_daily_demand(self) -> pd.Series:
        return self.daily_demand

    def get_dispatch(self) -> pd.DataFrame:
        return self.thermal_dispatch

    def get_unit_status(self) -> pd.DataFrame:
        return self.unit_status


class Visualizer:
    def __init__(self, model_name: str, ctime: str):
        self.fuel_color_map: dict = get_fuel_color_map()
        self.model_name: str = model_name
        # Need to get timestamp from OutputProcessor in 'YYYYMMDD_mmss' format
        self.ctime: str = ctime

    def plot_fuelmix_bar(
        self,
        dispatch: pd.DataFrame,
        demand: pd.Series,
        to_save: bool,
    ) -> None:
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
        ax.set_xlabel("Hour")

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
            figure_name = f"{self.ctime}_{self.model_name}_fuelmix.png"
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
        """Return an area plot of the fuel mix."""
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
        ax.set_xlabel("")

        legend = fig.legend(
            loc="outside lower center",
            ncols=4,
            fontsize="small",
            bbox_to_anchor=(0.5, -0.1),
        )
        ax.set_ylabel("Power (MW)")
        ax.set_ylim(bottom=0)

        if to_save:
            figure_name = f"{self.ctime}_{self.model_name}_fuelmix.png"
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
        thermal_units: list[str],
        full_max_cap: dict[str, float],
        to_save: bool,
    ) -> None:
        """Plot the on/off status of individual thermal units"""

        for unit_g in thermal_units:
            # Extract the dispatch of each thermal unit and plot the value
            df1 = thermal_dispatch[thermal_dispatch.node == unit_g]
            df2 = unit_status[unit_status["node"] == unit_g]

            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()

            ax1.step(df1["hour"], df1["value"], where="mid", color="b", label="Power")
            # If ymax is too low, then we cannot see the blue line
            ax1.set_ylim(bottom=0, top=full_max_cap[unit_g] * 1.05)
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
                    get_output_dir(), f"{self.ctime}_unit_plots"
                )
                if not os.path.exists(unit_plot_folder):
                    os.mkdir(unit_plot_folder)

                fig.savefig(
                    os.path.join(
                        unit_plot_folder, f"{self.ctime}_{self.model_name}_{unit_g}.png"
                    ),
                    dpi=350,
                )

            plt.show()
