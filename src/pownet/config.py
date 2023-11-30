import configparser
import os
from pownet.folder_sys import get_pownet_dir



def get_config() -> configparser.ConfigParser:
    config_file = os.path.join(get_pownet_dir(), 'user_config.ini')
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


def is_warmstart() -> bool:
    ''' Get the user specified warmstart parameter.
    '''
    config = get_config()
    return config.getboolean('GUROBI', 'WARMSTART')


def get_line_capacity_factor() -> float:
    ''' The safety margin to impose on the transmission lines.
    The default value is 0.75 based on the legacy approach.
    '''
    config = get_config()
    return config.getfloat('POWNET', 'LINE_CAPACITY_FACTOR')

def get_line_loss_factor() -> float:
    ''' The safety margin to impose on the transmission lines.
    The default value is 0.75 based on the legacy approach.
    '''
    config = get_config()
    return config.getfloat('POWNET', 'LINE_LOSS_FACTOR')


def get_spin_reserve_factor() -> float:
    ''' This is the amount of spinning reserve needed as a fraction
    of the system-wide generation capacity. The default value is 0.15.
    '''
    config = get_config()
    return config.getfloat('POWNET', 'SPIN_RESERVE')


def get_shortfall_penalty() -> int:
    ''' The cost of failing to meet demand in $/MW.
    The default shortfall cost is $1000/MW
    '''
    config = get_config()
    return config.getint('POWNET', 'SHORTFALL_PENALTY')


def get_spin_reserve_penalty() -> int:
    ''' The cost of failing to meet the spinning reserve requirement in $/MW.
    The default shortfall cost is $1000/MW.
    '''
    config = get_config()
    return config.getint('POWNET', 'RESERVE_PENALTY')


def get_mip_gap() -> float:
    ''' Gurobi MIPGAP significantly affect computation time.
    '''
    config = get_config()
    return config.getfloat('GUROBI', 'MIPGAP')


def get_to_log() -> bool:
    ''' Gurobi MIPGAP significantly affect computation time.
    '''
    config = get_config()
    return config.getboolean('GUROBI', 'LOGTOCONSOLE')

