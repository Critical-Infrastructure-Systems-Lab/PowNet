"""visualizer.py: This module contains the Visualizer class, which provides methods to visualize the output from PowNet.
"""

import os

import contextily as cx
import geopandas as gpd
import matplotlib as mpl
from matplotlib.colors import ListedColormap
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pownet.data_utils import get_fuel_color_map, create_geoseries_columns


class Visualizer:
    def __init__(self, model_id: str) -> None:
        self.model_id: str = model_id
        self.fuel_color_map: dict = get_fuel_color_map()

    def plot_fuelmix_bar(
        self,
        dispatch: pd.DataFrame,
        demand: pd.Series,
        output_folder: str = None,
    ) -> None:
        """Create a bar plot of the fuel mix.

        Args:
            dispatch (pd.DataFrame): The dispatch of each generator.
            demand (pd.Series): The demand of the system.
            output_folder (str): If specified, then the plot is saved in the folder.

        Returns:
            None
        """
        # Use total_timesteps to index demand because
        # the length of demand can be longer than the simulation hours
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
            ncols=5,
            fontsize="small",
            bbox_to_anchor=(0.5, -0.12),
        )
        ax.set_ylabel("Power (MW)")
        ax.set_ylim(top=(demand[:total_timesteps].max() * 1.30).values[0])

        if output_folder is not None:
            figure_name = f"{self.model_id}_fuelmix.png"
            fig.savefig(
                os.path.join(output_folder, figure_name),
                bbox_extra_artists=(legend,),
                bbox_inches="tight",
                dpi=350,
            )
        plt.show()

    def plot_fuelmix_area(
        self,
        dispatch: pd.DataFrame,
        demand: pd.Series,
        output_folder: str = None,
    ) -> None:
        """Create an area plot of the fuel mix.

        Args:
            dispatch (pd.DataFrame): The dispatch of each generator.
            demand (pd.Series): The demand of the system.
            output_folder (str): If specified, then the plot is saved in the folder.

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
            ncols=5,
            fontsize="small",
            bbox_to_anchor=(0.5, -0.12),
        )
        ax.set_ylabel("Power (MW)")
        ax.set_ylim(top=(demand[:total_timesteps].max() * 1.30).values[0])

        if output_folder is not None:
            figure_name = f"{self.model_id}_fuelmix.png"
            fig.savefig(
                os.path.join(output_folder, figure_name),
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
        output_folder: str = None,
    ) -> None:
        """Plot the on/off status of individual thermal units

        Args:
            thermal_dispatch (pd.DataFrame): The dispatch of each thermal unit.
            unit_status (pd.DataFrame): The status of each thermal unit.
            thermal_rated_capacity (dict[str, float]): Rated capacity of each thermal unit.
            output_folder (str): If specified, then the plot is saved in the folder.

        Returns:
            None

        """
        thermal_units = thermal_dispatch["node"].unique()

        for unit in thermal_units:
            # Extract the dispatch of each thermal unit and plot the value
            df1 = thermal_dispatch[thermal_dispatch.node == unit]
            df2 = unit_status[unit_status["node"] == unit]

            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()

            ax1.step(df1["hour"], df1["value"], where="mid", color="b", label="Power")
            # If ymax is too low, then we cannot see the blue line
            ax1.set_ylim(bottom=0, top=thermal_rated_capacity[unit] * 1.05)
            ax1.tick_params(axis="x", labelrotation=45)
            ax1.set_xlabel("Hour")
            ax1.set_ylabel("Power (MW)")

            ax2.bar(
                df2["hour"], df2["value"], color="k", alpha=0.2, label="Unit status"
            )
            ax2.set_ylim(bottom=0, top=1)
            ax2.set_ylabel("Unit Status")
            plt.title(unit)

            if output_folder is not None:
                unit_plot_folder = os.path.join(
                    output_folder, f"{self.model_id}_unit_plots"
                )
                if not os.path.exists(unit_plot_folder):
                    os.mkdir(unit_plot_folder)

                fig.savefig(
                    os.path.join(unit_plot_folder, f"{unit}.png"),
                    dpi=350,
                )
            plt.show()

    def plot_mean_thermal_unit_hourly_status(
        self, thermal_unit_mean_hourly_status: pd.DataFrame, output_folder: str = None
    ) -> None:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.imshow(thermal_unit_mean_hourly_status.T, cmap="binary", aspect="auto")
        ax.set_xlabel("Hour of the day")
        ax.set_ylabel("Thermal unit ID")
        ax.set_title("Mean hourly status of thermal units")

        # Create a colorbar
        norm = mpl.colors.Normalize(vmin=0, vmax=1)
        cbar = plt.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap="binary"), ax=ax)
        cbar.set_label("Unit status")

        legend = fig.legend(
            loc="outside lower center",
            fontsize="small",
            bbox_to_anchor=(0.5, -0.12),
        )

        if output_folder is not None:
            figure_name = f"{self.model_id}_thermal_unit_status.png"
            fig.savefig(
                os.path.join(output_folder, figure_name),
                bbox_extra_artists=(legend,),
                bbox_inches="tight",
                dpi=350,
            )
        plt.show()

    def plot_lmp(
        self,
        lmp_df: pd.DataFrame,
        output_folder: str = None,
        max_ylim: float = 200,
    ) -> None:
        """Plots unique locational marginal price (LMP) timeseries.
        For each unique LMP timeseries, a representative node is chosen
        based on ordering in the dataframe.

        Args:
            lmp_df (pd.DataFrame): LMP timeseries.
            output_folder (str): If specified, then the plot is saved in the folder.
            max_ylim (float): Maximum y-axis limit.

        Returns:
            None

        """
        # Find uni
        unique_lmp = lmp_df.copy().T.drop_duplicates().T

        fig, ax = plt.subplots()
        unique_lmp.plot(ax=ax, linewidth=2)
        ax.set_xlabel("Hour")
        ax.set_ylabel("LMP ($/MWh)")
        # Place legend at the bottom
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4)
        ax.set_ylim(top=max_ylim)

        # Adjust layout to prevent legend from being cut off
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.2)

        if output_folder is not None:
            figure_name = f"{self.model_id}_lmp.png"
            fig.savefig(
                os.path.join(output_folder, figure_name),
                dpi=350,
            )
        plt.show()

    def plot_line_usage(
        self,
        max_line_usage: pd.DataFrame,
        output_folder: str,
    ) -> None:
        """Flow variables must have the max_line_usage column"""
        max_line_usage = create_geoseries_columns(max_line_usage)
        # There should be three geoseries columns: source_location,
        # sink_location, and geometry.
        max_line_usage_gdf = gpd.GeoDataFrame(
            max_line_usage, geometry="geometry", crs="EPSG:4326"
        )

        def get_linewidth(capacity):
            min_capacity = max_line_usage.rated_capacity.min()
            max_capacity = max_line_usage.rated_capacity.max()
            min_linewidth = 2
            max_linewidth = 6
            # Scale capacity to between 1 and 10 to avoid log(0) errors
            scaled_capacity = 1 + 9 * (capacity - min_capacity) / (
                max_capacity - min_capacity
            )
            log_capacity = np.log10(scaled_capacity)
            # Scale the log value to the desired linewidth range.
            return min_linewidth + (log_capacity / np.log10(10)) * (
                max_linewidth - min_linewidth
            )

        max_line_usage_gdf["linewidth"] = max_line_usage_gdf["rated_capacity"].apply(
            get_linewidth
        )

        # Bin the 'line_usage' column into 5 quantiles for plotting
        # colors = ["#000004", "#3b0f6f", "#8c2981", "#dd4968", "#fd9347"]
        colors = ["#fdd0a2", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603"]
        labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]

        bins = [-0.01, 0.2, 0.4, 0.6, 0.8, 1.0]
        max_line_usage_gdf["usage_bin"] = pd.cut(
            max_line_usage_gdf["max_line_usage"],
            bins=bins,
            right=True,
            labels=labels,
        )

        # Plot
        ax = max_line_usage_gdf.plot(
            column="usage_bin",
            figsize=(13, 7),
            cmap=ListedColormap(colors),
            linewidth=max_line_usage_gdf["linewidth"],
            legend=True,
            legend_kwds={
                "title": "Max line capacity rate",
                "loc": "upper left",
                "bbox_to_anchor": (1, 1),
            },
        )
        max_line_usage_gdf["sink_location"].plot(ax=ax, color="k", markersize=5)
        max_line_usage_gdf["source_location"].plot(ax=ax, color="k", markersize=5)

        cx.add_basemap(
            ax, crs=max_line_usage_gdf.crs, source=cx.providers.CartoDB.Positron
        )
        ax.set_axis_off()

        # Format plots
        # Adjust layout to prevent legend from being cut off
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.2)

        if output_folder is not None:
            figure_name = f"{self.model_id}_line_usage.png"
            fig = ax.get_figure()
            fig.savefig(
                os.path.join(output_folder, figure_name),
                dpi=350,
            )
        plt.show()

    def plot_unit_storage_state(
        self,
        hourly_storage_charge: pd.Series,
        hourly_storage_discharge: pd.Series,
        hourly_storage_state: pd.Series,
        output_folder: str = None,
    ) -> None:
        """
        Plot the hourly activity of the energy storage units.

        Args:
            hourly_storage_charge (pd.Series): Hourly charge data.
            hourly_storage_discharge (pd.Series): Hourly discharge data.
            hourly_storage_state (pd.Series): Hourly storage state data.
        """
        storage_units = hourly_storage_charge.columns
        for unit in storage_units[:2]:
            fig, axes = plt.subplots(
                2, 1, figsize=(10, 6), sharex=True, height_ratios=[3, 1]
            )  # Set height ratios

            # Plot storage fraction
            axes[0].plot(hourly_storage_state.index, hourly_storage_state[unit].values)
            axes[0].set_ylabel("Storage Fraction")

            axes[0].set_title(f"{unit} hourly storage state")

            # Plot charge and discharge as bar chart
            axes[1].bar(
                hourly_storage_charge.index,
                hourly_storage_charge[unit].values,
                label="Charge",
            )
            axes[1].bar(
                hourly_storage_discharge.index,
                -1 * hourly_storage_discharge[unit].values,
                label="Discharge",
            )
            axes[1].set_ylabel("Power (MW)")
            axes[1].set_xlabel("Hour")
            # axes[1].legend()

            plt.tight_layout()

            if output_folder is not None:
                unit_plot_folder = os.path.join(
                    output_folder, f"{self.model_id}_energy_storage_plots"
                )
                if not os.path.exists(unit_plot_folder):
                    os.mkdir(unit_plot_folder)

                fig.savefig(
                    os.path.join(unit_plot_folder, f"{unit}.png"),
                    dpi=350,
                )
            plt.show()

    def plot_generation_by_contracts(self, contract_generation: pd.DataFrame) -> None:
        fig, ax = plt.subplots(figsize=(5, 8))
        df_to_plot = contract_generation.sort_values(by=["value"], ascending=False)
        df_to_plot.plot(ax=ax, kind="bar", linewidth=2, legend=False)
        ax.set_ylabel("Generation (MWh)")
        plt.show()
