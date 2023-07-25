

unit_g = 'pGas'

model.update()

CONS = model.getConstrs()

for con in CONS:
    print(model.getRow(con), con.sense, con.rhs)


def c_trajec_up_bound_short(unit_g):
    for unit_g in thermal_units:
        time_RU = floor((max_cap[unit_g] - SU[unit_g])/RU[unit_g])
        min_val = min(TU[unit_g]-1, time_RU)
        
        model.addConstrs(
         (
             pbar[unit_g, t]
             <= (max_cap[unit_g] - min_cap[unit_g])*u[unit_g, t]
                 - gp.quicksum(
                     max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]*v[unit_g, t-i]
                     for i in range(0, min_val+1)
                     )
            for t in timesteps
                 ),
         name = 'trajecUpBoundShort' + f'_{unit_g}'
         )