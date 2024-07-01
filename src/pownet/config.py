import configparser
import os
from pownet.folder_sys import get_pownet_dir


# Create global variable to only read the config file once
config_file = os.path.join(get_pownet_dir(), 'user_config.ini')
CONFIG = configparser.ConfigParser()
CONFIG.read(config_file)



def get_config() -> configparser.ConfigParser:
    return CONFIG




#  [POWNET]
def get_line_capacity_factor() -> float:
    ''' The safety margin to impose on the transmission lines.
    The default value is 0.75 based on the legacy approach.
    '''
    return CONFIG.getfloat('POWNET', 'LINE_CAPACITY_FACTOR')

def get_line_loss_factor() -> float:
    ''' The safety margin to impose on the transmission lines.
    The default value is 0.75 based on the legacy approach.
    '''
    return CONFIG.getfloat('POWNET', 'LINE_LOSS_FACTOR')


def get_spin_reserve_factor() -> float:
    ''' This is the amount of spinning reserve needed as a fraction
    of the system-wide generation capacity. The default value is 0.15.
    '''
    return CONFIG.getfloat('POWNET', 'SPIN_RESERVE')


def get_shortfall_penalty() -> int:
    ''' The cost of failing to meet demand in $/MW.
    The default shortfall cost is $1000/MW
    '''
    return CONFIG.getint('POWNET', 'SHORTFALL_PENALTY')


def get_spin_reserve_penalty() -> int:
    ''' The cost of failing to meet the spinning reserve requirement in $/MW.
    The default shortfall cost is $1000/MW.
    '''
    return CONFIG.getint('POWNET', 'RESERVE_PENALTY')

#  [Gurobi]
def is_warmstart() -> bool:
    ''' Get the user specified warmstart parameter.
    '''
    return CONFIG.getboolean('GUROBI', 'WARMSTART')
    
def get_mip_gap() -> float:
    ''' Gurobi MIPGAP significantly affect computation time.
    '''
    return CONFIG.getfloat('GUROBI', 'MIPGAP')


def get_to_log() -> bool:
    ''' Gurobi MIPGAP significantly affect computation time.
    '''
    return CONFIG.getboolean('GUROBI', 'LOGTOCONSOLE')


def get_timelimit() -> float:
    ''' Enforces timelimit to solve the problem. 
    '''


# [USER Defined Inputs]
def get_modelname() -> str:
    ''' Get the user defined model name.
    '''
    return CONFIG.get('USER DEFINED INPUTS', 'MODEL_NAME')

def get_stepbystep() -> bool:
    ''' Get the user option for step-by-step version.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'STEP_BY_STEP')

def get_onestep() -> bool:
    ''' Get the user option for running one step version.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'ONE_STEP')

def get_usegurobi() -> bool:
    ''' Get the user option for using Gurobi.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'use_gurobi')

def get_steps() -> int:
    ''' Get the user selection for number of steps.
    '''
    return CONFIG.getint('USER DEFINED INPUTS', 'STEPS')

def get_simday() -> int:
    ''' Get the user selection for simulated day.
    '''
    return CONFIG.getint('USER DEFINED INPUTS', 'SIM_DAY')

def get_timehorizon() -> int:
    ''' Get the user selection for simulated time horizon in hours.
    '''
    return CONFIG.getint('USER DEFINED INPUTS', 'T')

def get_saveresults() -> bool:
    ''' Get the user option for saving results.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'SAVE_RESULT')

def get_saveplots() -> bool:
    ''' Get the user option for saving plots.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'SAVE_PLOT')
    return CONFIG.getfloat('GUROBI', 'TIMELIMIT')

def get_resreop() -> bool:
    ''' Get the user option for reservoir reoperation.
    '''
    return CONFIG.getboolean('USER DEFINED INPUTS', 'RES_REOP')
