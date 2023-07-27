#aaaa

unit_g = 'pGas'

model.update()

CONS = model.getConstrs()

for con in CONS:
    print(model.getRow(con), con.sense, con.rhs)


set_objective()
c_link_p()
c_link_unit_status()
# c_min_up_init()
# c_min_down_init()
# c_min_up()
# c_min_down()
c_p_bound()
# c_switch_ramp_bound()
# c_peak_up_bound()
# c_peak_down_bound()
# c_trajec_up_bound()
# c_trajec_down_bound()
# c_ramp_up()
# c_ramp_down()
# c_angle_dff()
# c_max_flow()
# c_ref_node()
c_flow_balance()
# c_reserve_req()
c_renewables_bound()

model.optimize()
