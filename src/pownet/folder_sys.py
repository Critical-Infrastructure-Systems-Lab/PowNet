import os




def get_pownet_dir() -> str:
    ''' Does not assume the user saves the folder under their home directory
    '''
    return os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__))))


def get_output_dir() -> str:
    return os.path.join(get_pownet_dir(), 'outputs')


def get_input_dir() -> str:
    return os.path.join(get_pownet_dir(), 'user_inputs')


def get_temp_dir() -> str:
    return os.path.join(get_pownet_dir(), 'temp')



def get_model_dir() -> str:
    return os.path.join(get_pownet_dir(), 'model_library') 


def get_home_dir() -> str:
    return os.path.expanduser('~')



