from datetime import datetime
import os

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pownet.core.input import SystemInput
from pownet.folder_sys import get_output_dir


def format_variable_fueltype(
        df: pd.DataFrame,
        vartype: str,
        fuel_type: str
        ) -> None:
        output_df = df[df['vartype'] == vartype]
        # output_df = output_df.rename(columns={'value':'dispatch'})
        output_df = output_df.reset_index(drop=True)
        output_df['fuel_type'] = fuel_type
        return output_df


class Visualizer():
    def __init__(self) -> None:
        self.model_name = None
        
        self.status: pd.DataFrame = None
        self.fuelmap: dict[str, str] = None
        self.thermal_units: list[str] = None
        self.max_cap: dict[str, float] = None
        
        self.thermal_dispatch: pd.DataFrame = None
        self.rnw_dispatch: pd.DataFrame = None
        self.shortfall: pd.DataFrame = None


    
    def load(self, df: pd.DataFrame, system_input: SystemInput, model_name) -> None:
        self.model_name = model_name
        
        self.status = df[df['vartype'] == 'status']
        self.thermal_units = system_input.thermal_units
        self.fuelmap = system_input.fuelmap[['name', 'fuel_type']]\
            .set_index('name').to_dict()['fuel_type']
        self.max_cap = system_input.max_cap
        
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
        self.p_import = format_variable_fueltype(df=df, vartype='pimp', fuel_type='import')

        # There are positive and negative shortfalls
        self.shortfall_pos = format_variable_fueltype(
            df=df, vartype='s_pos', fuel_type='shortfall_positive')

        self.shortfall_neg = format_variable_fueltype(
            df=df, vartype='s_neg', fuel_type='shortfall_negative')
        
        # # Fix numerical issue
        # self.shortfall_pos.loc[self.shortfall_pos['value'] <= 0, 'value'] = 0
        # self.shortfall_neg.loc[self.shortfall_neg['value'] <= 0, 'value'] = 0

    def plot_fuelmix(self, to_save: bool) -> None:
        total_dispatch = pd.concat(
            [self.thermal_dispatch, self.rnw_dispatch, self.p_import, self.shortfall_pos, self.shortfall_neg], 
            axis = 0)
        
        total_dispatch = total_dispatch.reset_index(drop=True)
        total_dispatch = total_dispatch[['fuel_type', 'value', 'hour']]\
            .groupby(['fuel_type', 'hour']).sum()
            
        total_dispatch = total_dispatch.reset_index()
        total_dispatch = total_dispatch.pivot(
            columns=['hour'], index=['fuel_type']).T\
            .reset_index(drop=True)
        total_dispatch.index += 1
        
        # Ensure all close to zero values are zero
        for col in total_dispatch.columns:
            total_dispatch.loc[np.isclose(total_dispatch[col], 0), col] = 0
            
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
                get_output_dir(), f'{c_time}_{self.model_name}_fuelmix.png'))
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
                df1['hour'], df1['value'], 
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
                    f'{c_time}_{self.model_name}_{unit_g}.png'))
            plt.show()