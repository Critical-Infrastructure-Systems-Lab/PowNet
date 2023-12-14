from datetime import datetime
import math
import os

import pandas as pd
import matplotlib.pyplot as plt

from pownet.core.input import SystemInput
from pownet.folder_sys import get_output_dir, get_database_dir
from pownet.processing.functions import get_dates


def format_variable_fueltype(
        df: pd.DataFrame,
        vartype: str,
        fuel_type: str
        ) -> pd.DataFrame:
    ''' Given a dataframe of outputs, filter for a vartype and assign the fuel type.
    Use this function for import, s_pos, and s_neg.
    '''
    output_df = df[df['vartype'] == vartype]
    output_df = output_df.reset_index(drop=True)
    output_df['fuel_type'] = fuel_type
    return output_df


def get_fuel_color_map() -> dict:
    ''' Return a map of fuel type to its color. This is defined in the database folder.
    '''
    fuel_color_map = pd.read_csv(
        os.path.join(get_database_dir(), 'fuels.csv'), 
        header=0,
        usecols = ['name', 'color']
        ).set_index('name').to_dict()['color']
    return fuel_color_map



class Visualizer():
    def __init__(self) -> None:
        self.model_name = None
        self.year = None
        
        self.status: pd.DataFrame = None
        self.fuelmap: dict[str, str] = None
        self.thermal_units: list[str] = None
        self.full_max_cap: dict[str, float] = None
        
        self.thermal_dispatch: pd.DataFrame = None
        self.rnw_dispatch: pd.DataFrame = None
        self.shortfall: pd.DataFrame = None
        self.total_dispatch: pd.DataFrame = None
        
        self.fuel_mix_order: pd.DataFrame = None
        self.fuel_color_map: dict = None
        self.total_timesteps: int = None
        
        self.demand: pd.Series = None


    
    def load(self, df: pd.DataFrame, system_input: SystemInput, model_name) -> None:
        self.model_name = model_name
        self.year = system_input.year
        
        # For saving files
        self.ctime = datetime.now().strftime("%Y%m%d_%H%M")
        
        self.status = df[df['vartype'] == 'status']
        self.thermal_units = system_input.thermal_units
        self.fuelmap = system_input.fuelmap[['name', 'fuel_type']]\
            .set_index('name').to_dict()['fuel_type']
        self.full_max_cap = system_input.full_max_cap
        
        # Generation from thermal units
        self.thermal_dispatch = df[df['vartype'] == 'dispatch']
        self.thermal_dispatch = self.thermal_dispatch
        self.thermal_dispatch = self.thermal_dispatch.reset_index(drop=True)
        self.thermal_dispatch['fuel_type'] = self.thermal_dispatch.apply(
            lambda x: self.fuelmap[x['node']], axis=1)

        # Generation from renewables
        self.rnw_dispatch = df[df['vartype'] == 'prnw']
        # self.rnw_dispatch = self.rnw_dispatch.rename(columns={'value':'dispatch'})
        self.rnw_dispatch = self.rnw_dispatch.reset_index(drop=True)
        self.rnw_dispatch['fuel_type'] = self.rnw_dispatch.apply(
            lambda x: self.fuelmap[x['node']], axis=1)
        
        # Generation from import nodes
        self.p_import = format_variable_fueltype(
            df=df, vartype='pimp', fuel_type='import'
            )
        # There are positive and negative shortfalls
        self.shortfall_pos = format_variable_fueltype(
            df=df, vartype='s_pos', fuel_type='shortfall'
            )
        self.shortfall_neg = format_variable_fueltype(
            df=df, vartype='s_neg', fuel_type='curtailment'
            )
        self.demand = system_input.demand.sum(axis=1)
        
        # Dispatch is the power needed to satisfy system requirements
        self.total_dispatch = pd.concat(
            [
                self.thermal_dispatch,
                self.rnw_dispatch,
                self.p_import,
                self.shortfall_pos,
                self.shortfall_neg
                ], 
            axis = 0
            )
        self.total_dispatch = self.total_dispatch.reset_index(drop=True)
        self.total_dispatch = self.total_dispatch[['fuel_type', 'value', 'hour']]\
            .groupby(['fuel_type', 'hour']).sum()
            
        self.total_dispatch = self.total_dispatch.reset_index()
        self.total_dispatch = self.total_dispatch.pivot(
            columns=['hour'], index=['fuel_type']).T\
            .reset_index(drop=True)
        self.total_dispatch.index += 1
        
        # Define the order of fuel mix. Baseload at the bottom, 
        # renewables in the middle, then peaker plants, and shortfall
        self.fuel_mix_order = pd.read_csv(
            os.path.join(get_database_dir(), 'fuels.csv'),
            header = 0,
            )['name']
        self.fuel_mix_order = [fuel for fuel in self.fuel_mix_order if fuel in self.total_dispatch.columns]
        self.total_dispatch = self.total_dispatch[self.fuel_mix_order]
        
        # We have a pre-defined set of colors for fuel types
        self.fuel_color_map = get_fuel_color_map()
        self.total_timesteps = self.total_dispatch.shape[0]
        

    def plot_fuelmix(
            self,
            to_save: bool,
            output_folder: str = None,
            figure_name: str = None
            ) -> None:
        
        # Plotting section
        fig, ax = plt.subplots(figsize=(8, 5))
        # If shorter than 3 days, then we do a barplot
        if math.ceil(self.total_timesteps/24) < 3:
            # Bar plot
            self.total_dispatch.plot.bar(
                stacked = True,
                ax = ax,
                linewidth = 0,
                color = self.fuel_color_map,
                legend = False
                )
            ax.plot(
                range(0, self.total_timesteps), 
                self.demand[:self.total_timesteps],
                color = 'k',
                linewidth = 2,
                linestyle = ':',
                label = 'demand'
                )
            ax.set_xlabel('Hour')
            
        elif math.ceil(self.total_timesteps/24) < 62:
            # If we are plotting longer than 2 days, then the area plot
            # is better at visualizing the fuel mix.
            self.total_dispatch.plot.area(
                stacked = True,
                ax = ax,
                linewidth = 0,
                color = self.fuel_color_map,
                legend = False
                )
            ax.plot(
                self.demand[:self.total_timesteps],
                color = 'k',
                linewidth = 2,
                linestyle = ':',
                label = 'demand'
                )
            ax.set_xlabel('Hour')
        else:
            # Do bar plot by month
            dates = get_dates(year=self.year)
            dates.index += 1
            
            monthly_dispatch = self.total_dispatch.copy()
            monthly_dispatch['month'] = dates['date'].dt.to_period('M')
            monthly_dispatch = monthly_dispatch.groupby('month').sum()
            monthly_dispatch.index = monthly_dispatch.index.strftime('%b')
            
            monthly_demand = self.demand[:self.total_timesteps].to_frame()
            monthly_demand.columns = ['demand']
            monthly_demand['month'] = dates['date'].dt.to_period('M')
            monthly_demand = monthly_demand.groupby('month').sum()
            monthly_demand.index = monthly_demand.index.strftime('%b')
            
            monthly_dispatch.plot.bar(
                stacked = True,
                ax = ax,
                linewidth = 0,
                color = self.fuel_color_map,
                legend = False
                )
            ax.plot(
                monthly_demand,
                color = 'k',
                linewidth = 2,
                linestyle = ':',
                label = 'demand'
                )
            ax.set_xlabel('')
            
        # Plot formatting
        legend = fig.legend(
            loc = 'outside lower center',
            # title = 'Legend',
            ncols = 4,
            fontsize = 'small',
            bbox_to_anchor=(0.5, -0.1)
            )
        ax.set_ylabel('Power (MW)')
        ax.set_ylim(bottom=0)
        
        if to_save:
            
            if not output_folder:
                output_folder = get_output_dir()
            
            if not figure_name:
                figure_name = f'{self.ctime}_{self.model_name}_fuelmix.png'
                
            fig.savefig(os.path.join(output_folder, figure_name),
                bbox_extra_artists = (legend,),
                bbox_inches = 'tight',
                dpi = 350
                )
        plt.show()
        
        
    
    def plot_area_fuelmix(self) -> None:
        ''' Return an area plot of the fuel mix
        '''
        # Aggregate dispatch by day
        dates = get_dates(year=self.year)
        dates.index += 1
        
        daily_dispatch = self.total_dispatch.copy()
        daily_dispatch = daily_dispatch.groupby(daily_dispatch.index // 24).mean()
        
        daily_demand = self.demand.groupby(self.demand.index // 24).mean()
        
        # Plotting
        fig, ax = plt.subplots(figsize=(8, 5))
        daily_dispatch.plot.area(
            stacked = True,
            ax = ax,
            linewidth = 0,
            color = self.fuel_color_map,
            legend = False
            )
        ax.plot(
            daily_demand,
            color = 'k',
            linewidth = 2,
            linestyle = ':',
            label = 'demand'
            )
        ax.set_xlabel('Day')
        
        fig.legend(
            loc = 'outside lower center',
            # title = 'Legend',
            ncols = 4,
            fontsize = 'small',
            bbox_to_anchor=(0.5, -0.1)
            )
        ax.set_ylabel('Power (MW)')
        ax.set_ylim(bottom=0)
        plt.show()
    
    
    def plot_thermal_units(
            self,
            to_save: bool,
            ) -> None:
        ''' Plot the on/off status of individual thermal units
        '''
        for unit_g in self.thermal_units:
            # Extract the dispatch of each thermal unit and plot the value
            df1 = self.thermal_dispatch[self.thermal_dispatch.node == unit_g]
            df2 = self.status[self.status['node'] == unit_g]
            
            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()
            
            ax1.step(
                df1['hour'], df1['value'], 
                where = 'mid', 
                color = 'b', 
                label = 'Power'
                )
            # If ymax is too low, then we cannot see the blue line
            ax1.set_ylim(
                bottom = 0, 
                top = self.full_max_cap[unit_g]*1.05
                )
            ax1.tick_params(axis='x', labelrotation=45)
            ax1.set_xlabel('Hour')
            ax1.set_ylabel('Power (MW)')
            
            ax2.bar(
                df2['hour'], df2['value'], 
                color = 'k', 
                alpha = 0.2,
                label = 'Unit status'
                )
            ax2.set_ylim(
                bottom = 0, 
                top = 1
                )
            ax2.set_ylabel('Unit Status')

            plt.title(unit_g)
            
            if to_save:
                unit_plot_folder = os.path.join(get_output_dir(), f'{self.ctime}_unit_plots')
                if not os.path.exists(unit_plot_folder):
                    os.mkdir(unit_plot_folder)
                    
                fig.savefig(
                    os.path.join(unit_plot_folder,  f'{self.ctime}_{self.model_name}_{unit_g}.png'),
                    dpi = 350)
                
            plt.show()