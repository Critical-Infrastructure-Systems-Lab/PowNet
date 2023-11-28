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