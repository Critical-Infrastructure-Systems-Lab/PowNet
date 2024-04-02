import configparser
import os
from pownet.folder_sys import get_pownet_dir


# Create global variable to only read the config file once
config_file = os.path.join(get_pownet_dir(), 'user_config.ini')
CONFIG = configparser.ConfigParser()
CONFIG.read(config_file)



def get_config() -> configparser.ConfigParser:
    return CONFIG


def is_warmstart() -> bool:
    ''' Get the user specified warmstart parameter.
    '''
    return CONFIG.getboolean('GUROBI', 'WARMSTART')


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
    return CONFIG.getfloat('GUROBI', 'TIMELIMIT')

