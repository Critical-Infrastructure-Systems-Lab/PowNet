from datetime import datetime
import os

import pandas as pd
import matplotlib.pyplot as plt

from pownet.core.input import SystemInput
from pownet.folder_sys import get_output_dir




class Visualizer():
    def __init__(self) -> None:
        self.status: pd.DataFrame = None
        self.fuelmap: dict[str, str] = None
        self.thermal_units: list[str] = None
        self.max_cap: dict[str, float] = None
        
        self.thermal_dispatch: pd.DataFrame = None
        self.rnw_dispatch: pd.DataFrame = None
        self.shortfall: pd.DataFrame = None


    
    def load(self, df: pd.DataFrame, system_input: SystemInput) -> None:
        
        self.status = df[df['vartype'] == 'status']
        self.thermal_units = system_input.thermal_units
        self.fuelmap = system_input.fuelmap[['name', 'fuel_type']]\
            .set_index('name').to_dict()['fuel_type']
        self.max_cap = system_input.max_cap
        

        # Create a map of {unit_g: {hour: status}} to calculate the thermal dispatch
        status_map = self.status[['node', 'hour', 'value']]\
            .set_index(['node', 'hour']).to_dict()['value']
        
        # Calculate thermal dispatch from the variable p
        self.thermal_dispatch = df[df['vartype'] == 'p']
        self.thermal_dispatch = self.thermal_dispatch[
            self.thermal_dispatch['node'].isin(self.thermal_units)]

        self.thermal_dispatch['dispatch'] = self.thermal_dispatch.apply(
            lambda x: x['value'] + system_input.min_cap[x['node']]*status_map[x['node'], x['hour']], 
            axis=1)
        
        self.thermal_dispatch = self.thermal_dispatch.drop('value', axis=1)
        self.thermal_dispatch = self.thermal_dispatch.reset_index(drop=True)
        
        self.thermal_dispatch['fuel_type'] = self.thermal_dispatch.apply(
            lambda x: self.fuelmap[x['node']], axis=1)
        
        # Calculate the renewable dispatch from the variable prnw
        self.rnw_dispatch = df[df['vartype'] == 'prnw']
        self.rnw_dispatch = self.rnw_dispatch.rename(columns={'value':'dispatch'})
        self.rnw_dispatch = self.rnw_dispatch.reset_index(drop=True)
        
        self.rnw_dispatch['fuel_type'] = self.rnw_dispatch.apply(
            lambda x: self.fuelmap[x['node']], axis=1)
        
        
        # Calculate the import from the variable pimp
        self.p_import = df[df['vartype'] == 'pimp']
        self.p_import = self.p_import.rename(columns={'value':'dispatch'})
        self.p_import = self.p_import.reset_index(drop=True)
        self.p_import['fuel_type'] = 'import'
        
        
        # Calculate the shortfall from the variable s_pos
        self.shortfall = df[df['vartype'] == 's_pos']
        self.shortfall = self.shortfall.rename(columns={'value':'dispatch'})
        self.shortfall = self.shortfall.reset_index(drop=True)
        self.shortfall['fuel_type'] = 'shortfall'
        
        # Fix numerical issue
        self.shortfall.loc[self.shortfall['dispatch'] <= 0, 'dispatch'] = 0
        
    
    def plot_fuelmix(self, to_save: bool) -> None:
        total_dispatch = pd.concat(
            [self.thermal_dispatch, self.rnw_dispatch, self.p_import, self.shortfall], 
            axis = 0)
        
        total_dispatch = total_dispatch.reset_index(drop=True)
        total_dispatch = total_dispatch[['fuel_type', 'dispatch', 'hour']]\
            .groupby(['fuel_type', 'hour']).sum()
            
        total_dispatch = total_dispatch.reset_index()
        total_dispatch = total_dispatch.pivot(
            columns=['hour'], index=['fuel_type']).T\
            .reset_index(drop=True)
            
        # Plotting section
        fig, ax = plt.subplots(figsize=(8, 5))
        # If we are plotting longer than 2 days, then the area plot
        # is better at visualizing the fuel mix.
        timesteps = total_dispatch.shape[0]
        if timesteps > 48:
            total_dispatch.plot.area(
                stacked = True,
                ax = ax,
                linewidth = 0
                )
        else:
            total_dispatch.plot.bar(
                stacked = True,
                ax = ax,
                linewidth = 0
                )
            
        ax.legend(bbox_to_anchor=(1, 1))
        ax.set_ylabel('Power (MW)')
        ax.set_xlabel('Hour')
        ax.set_ylim(bottom=0)
        
        if to_save:
            c_time = datetime.now().strftime("%Y%m%d_%H%M")
            plt.savefig(os.path.join(
                get_output_dir(), f'{c_time}_fuelmix.png'))
        plt.show()
                

    
    
    def plot_thermal_units(self, to_save: bool) -> None:
        ''' Plot the on/off status of individual thermal units
        '''
        for unit_g in self.thermal_units:
            # Extract the dispatch of each thermal unit and plot the value
            df1 = self.thermal_dispatch[self.thermal_dispatch.node == unit_g]
            df2 = self.status[self.status['node'] == unit_g]
            
            fig, ax1 = plt.subplots(figsize=(8, 5))
            ax2 = ax1.twinx()
            
            ax1.step(
                df1['hour'], df1['dispatch'], 
                where = 'mid', 
                color = 'b', 
                label = 'Power')
            
            ax2.bar(
                df2['hour'], df2['value'], 
                color = 'k', 
                alpha = 0.2,
                label = 'Unit status')
            
            ax1.set_xlabel('Hour')
            ax1.set_ylabel('Power (MW)')
            
            ax1.set_ylim(bottom=0)
            ax1.tick_params(axis='x', labelrotation=45)
        
            plt.title(unit_g)
            
            if to_save:
                c_time = datetime.now().strftime("%Y%m%d_%H%M")
                plt.savefig(
                    os.path.join(
                        get_output_dir(), 
                    f'{c_time}_{unit_g}.png'))
            plt.show()