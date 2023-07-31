#aaaa

from modeling3bin import *


def build_model():
    
    ########## Building the model
    set_objective()
    
    # Extra constraints
    # c_get_p()
    c_link_p()
    
    # Working constraints
    c_link_unit_status()
    c_p_bound()
    
    c_reserve_req()
    c_renewables_bound()
    
    c_flow_bound()
    c_ref_node()
    c_angle_dff()
    c_flow_balance()
    
    c_min_up_init()
    c_min_down_init()
    c_min_up()
    c_min_down()
    
    ######### Constraints to test
    # These three constraints might need to be replaced
    # c_switch_ramp_bound() # We do not have this for the three bins
    # c_peak_up_bound()
    # c_peak_down_bound()
    
    # # Trajectories up makes the model infeasible
    # c_trajec_up_bound()
    # c_trajec_down_bound()
    
    # Need to check these ramp up/down
    c_ramp_up()
    c_ramp_down()
    
    ######
    model.optimize()
    
    return model

######
# CONS = model.getConstrs()
# for con in CONS:
#     print(model.getRow(con), con.sense, con.rhs)

a = 'pBiomass'
t = 1