"""visualizer.py: This module contains the Visualizer class, which provides methods to visualize the output from PowNet."""

import os

import contextily as cx
import geopandas as gpd
import matplotlib as mpl
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
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
        ax.set_ylim(top=(demand[:total_timesteps].max() * 1.30))

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
        ax.set_ylim(top=(demand[:total_timesteps].max() * 1.30))

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
            df2 = unit_status[unit]

            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()

            ax1.step(df1["hour"], df1["value"], where="mid", color="b", label="Power")
            # If ymax is too low, then we cannot see the blue line
            ax1.set_ylim(bottom=0, top=thermal_rated_capacity[unit] * 1.05)
            ax1.tick_params(axis="x", labelrotation=45)
            ax1.set_xlabel("Hour")
            ax1.set_ylabel("Power (MW)")

            ax2.bar(df2.index, df2.values, color="k", alpha=0.2, label="Unit status")
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
        output_folder: str = None,
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
                max_capacity - min_capacity + 0.0001  # to avoid division by zero
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

        if output_folder:
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
        for unit in storage_units:
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

    def plot_power_flow(self, 
                        flow_variables: pd.DataFrame, 
                        figsize_per_line: tuple = (10, 2), # Note: height is for plot area of one subplot
                        fixed_legend_height_inches: float = 0.5) -> None:
        """
        Plots the power flow on transmission lines over time.

        Each unique transmission line (node_a to node_b) gets its own subplot.
        The y-axis label for each subplot is the line segment name.
        Legend is placed at the top center of the figure, occupying a fixed absolute height.
        Power flow is colored:
        - Green: Positive flow
        - Red: Negative flow
        - Black: Zero flow

        Args:
            flow_variables (pd.DataFrame): DataFrame with simulation results. Expected columns:
                                     'node_a', 'node_b', 'value', 'type' ('fwd' or 'bwd'), 'hour'.
            figsize_per_line (tuple): Tuple specifying (width, height_for_each_subplot_plot_area).
            fixed_legend_height_inches (float): Absolute height in inches for the legend area at the top.
        """
        lines = flow_variables[['node_a', 'node_b']].drop_duplicates().values.tolist()
        num_lines = len(lines)

        if num_lines == 0:
            print("No transmission lines to plot.")
            return

        fig_width = figsize_per_line[0]
        
        # Calculate the total height needed for the plot areas of all subplots
        plots_area_height_inches = figsize_per_line[1] * num_lines
        if plots_area_height_inches < 0: # Ensure non-negative plot height
            plots_area_height_inches = 0

        # Calculate the total figure height, including the fixed space for the legend
        total_figure_height_inches = plots_area_height_inches + fixed_legend_height_inches
        
        # Ensure total figure height is positive; if not, default to a minimum
        if total_figure_height_inches <= 0:
            total_figure_height_inches = max(fixed_legend_height_inches, 1.0) # Use legend height or 1 inch min

        fig, axes = plt.subplots(num_lines, 1,
                                 figsize=(fig_width, total_figure_height_inches), # Use the calculated total height
                                 sharex=True, squeeze=False)
        
        # Calculate the fraction of the total figure height that the legend area will occupy
        if total_figure_height_inches > 0: # Avoid division by zero
            legend_top_margin_fraction = fixed_legend_height_inches / total_figure_height_inches
        else: # Should be unreachable due to the check above
            legend_top_margin_fraction = 0.5 # Fallback: 50% for legend if total height is still 0

        # Ensure legend fraction is reasonable (e.g., not more than 80% if there are plots)
        # This prevents plots from being overly squished if their requested height is tiny.
        if plots_area_height_inches > 0 and legend_top_margin_fraction > 0.8:
            legend_top_margin_fraction = 0.8


        for i, line_nodes in enumerate(lines):
            ax = axes[i, 0] 
            node_a, node_b = line_nodes
            line_segment_name = f"{node_a} to {node_b}\nPower flow (MW)"

            line_df = flow_variables[(flow_variables['node_a'] == node_a) & (flow_variables['node_b'] == node_b)]

            if line_df.empty:
                ax.set_title(f"Power Flow: {line_segment_name} (No data)")
                ax.set_ylabel(line_segment_name)
                ax.text(0.5, 0.5, 'No data for this line',
                        horizontalalignment='center', verticalalignment='center',
                        transform=ax.transAxes)
                continue
            
            try:
                pivot_df = line_df.pivot_table(index='hour', columns='type', values='value', fill_value=0)
            except Exception as e:
                ax.set_title(f"Power Flow: {line_segment_name} (Error pivoting data)")
                ax.set_ylabel(line_segment_name)
                ax.text(0.5, 0.5, f'Error processing data: {e}',
                        horizontalalignment='center', verticalalignment='center',
                        transform=ax.transAxes)
                continue

            if 'fwd' not in pivot_df.columns:
                pivot_df['fwd'] = 0
            if 'bwd' not in pivot_df.columns:
                pivot_df['bwd'] = 0

            pivot_df = pivot_df.sort_index()
            net_flow = pivot_df['fwd'] - pivot_df['bwd']
            hours = net_flow.index

            if len(hours) < 2:
                if len(hours) == 1:
                    y_val = net_flow.iloc[0]
                    color = 'green' if y_val > 0 else ('red' if y_val < 0 else 'black')
                    ax.plot(hours[0], y_val, marker='o', color=color)
                ax.set_title(f"Power Flow: {line_segment_name} (Not enough data for line plot)")
                ax.set_ylabel(line_segment_name)
                if len(hours) > 0: 
                    ax.set_xlim(hours.min() -1 if pd.api.types.is_numeric_dtype(hours) else hours.min() - pd.Timedelta(days=1), 
                                hours.max() + 1 if pd.api.types.is_numeric_dtype(hours) else hours.max() + pd.Timedelta(days=1))
                continue

            for j in range(len(hours) - 1):
                x1, x2 = hours[j], hours[j+1]
                y1, y2 = net_flow.iloc[j], net_flow.iloc[j+1]

                x1_num = pd.to_numeric(x1)
                x2_num = pd.to_numeric(x2)
                
                if y1 == 0 and y2 == 0:
                    ax.plot([x1, x2], [y1, y2], color='black', linestyle='-')
                elif y1 * y2 >= 0: 
                    if y1 == 0: 
                        color = 'green' if y2 > 0 else ('red' if y2 < 0 else 'black')
                    elif y2 == 0: 
                        color = 'green' if y1 > 0 else ('red' if y1 < 0 else 'black')
                    else: 
                        color = 'green' if y1 > 0 else 'red'
                    ax.plot([x1, x2], [y1, y2], color=color, linestyle='-')
                else: 
                    if (y2 - y1) == 0: 
                        x_intersect_num = x1_num 
                    else:
                        x_intersect_num = x1_num - y1 * (x2_num - x1_num) / (y2 - y1)
                    
                    if isinstance(x1, (pd.Timestamp, np.datetime64)):
                        x_intersect = pd.Timestamp(x_intersect_num)
                    elif isinstance(x1, pd.Timedelta) or isinstance(x1, np.timedelta64):
                         x_intersect = pd.Timedelta(x_intersect_num, unit='ns')
                    else:
                        x_intersect = x_intersect_num

                    color1 = 'green' if y1 > 0 else 'red'
                    ax.plot([x1, x_intersect], [y1, 0], color=color1, linestyle='-')
                    color2 = 'green' if y2 > 0 else 'red'
                    ax.plot([x_intersect, x2], [0, y2], color=color2, linestyle='-')

            ax.axhline(0, color='gray', linestyle='--', linewidth=0.8)
            # ax.set_title(f"Power Flow: {line_segment_name}")
            ax.set_ylabel(line_segment_name)

        if num_lines > 0:
            axes[-1, 0].set_xlabel("Hour")

        legend_elements = [Line2D([0], [0], color='green', lw=2, label='Positive Flow'),
                           Line2D([0], [0], color='red', lw=2, label='Negative Flow'),
                           Line2D([0], [0], color='black', lw=2, label='Zero Flow')]

        fig.tight_layout()
        
        # Adjust the top of the subplots area to make space for the legend.
        # The subplots will occupy the space from y=0 to y=(1 - legend_top_margin_fraction)
        fig.subplots_adjust(top=(1 - legend_top_margin_fraction))

        # Define the bounding box for the legend at the top of the figure
        # y coordinate for bbox starts where subplots end and goes up by legend_top_margin_fraction
        legend_bbox_y_start = 1 - legend_top_margin_fraction
        legend_bbox = (0, legend_bbox_y_start, 1, legend_top_margin_fraction)

        fig.legend(handles=legend_elements,
                   loc='center',
                   bbox_to_anchor=legend_bbox,
                   ncol=3,
                   frameon=False)

        plt.show()
