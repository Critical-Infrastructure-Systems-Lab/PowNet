''' This file contains supporting functions to perform analysis.
'''
import os

import pandas as pd

from pownet.folder_sys import get_model_dir


def calc_percent_change(
        series_new: pd.Series,
        series_base: pd.Series,
        small_value: float = 0.0001) -> pd.Series:
    ''' Return a series of percentage change.
    '''
    percent_change = (abs(series_new - series_base) / (small_value + series_base) * 100).round(4)
    return percent_change


def get_total_load(model_name: str) -> pd.Series:
    ''' Return the total load of the system at each hour
    '''
    load = pd.read_csv(
        os.path.join(get_model_dir(), model_name, 'demand_export.csv'))
    return load.sum(axis=1)


def get_total_renewable(model_name: str) -> pd.Series:
    ''' Return the total renewable capacity of the system at each hour.
    '''
    renewables = pd.read_csv(
        os.path.join(get_model_dir(), model_name, 'renewable.csv'))
    return renewables.sum(axis=1)
    