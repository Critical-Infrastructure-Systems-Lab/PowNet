
import csv
import pandas as pd
import numpy as np


######=================================================########
######               Segment A.1                       ########
######=================================================########

SimDays = 365
SimHours = SimDays * 24
HorizonHours = 24  ##planning horizon (e.g., 24, 48, 72 hours etc.)
TransLoss = 0.075  ##transmission loss as a percent of generation
n1criterion = 0.75 ##maximum line-usage as a percent of line-capacity
res_margin = 0.15  ##minimum reserve as a percent of system demand
spin_margin = 0.50 ##minimum spinning reserve as a percent of total reserve

data_name = 'pownet_data_camb_2016'


######=================================================########
######               Segment A.2                       ########
######=================================================########

#read parameters for dispatchable resources (coal/gas/oil/biomass generators, imports) 
df_gen = pd.read_csv('data_camb_genparams.csv',header=0)

##hourly ts of dispatchable hydropower at each domestic dam
df_hydro = pd.read_csv('data_camb_hydro_2016.csv',header=0)

##hourly ts of dispatchable hydropower at each import dam
df_hydro_import = pd.read_csv('data_camb_hydro_import_2016.csv',header=0)

####hourly ts of dispatchable solar-power at each plant
##df_solar = pd.read_csv('data_solar.csv',header=0)   
##
####hourly ts of dispatchable wind-power at each plant
##df_wind = pd.read_csv('data_wind.csv',header=0)

##hourly ts of load at substation-level
df_load = pd.read_csv('data_camb_load_2016.csv',header=0) 

#capacity and susceptence of each transmission line (one direction)
df_trans1 = pd.read_csv('data_camb_transparam.csv',header=0)

#hourly minimum reserve as a function of load (e.g., 15% of current load)
df_reserves = pd.DataFrame((df_load.iloc[:,4:].sum(axis=1)*res_margin).values,columns=['Reserve'])

#capacity and susceptence of each transmission line (both directions)
df_trans2 = pd.DataFrame([df_trans1['sink'],df_trans1['source'],df_trans1['linemva'],df_trans1['linesus']]).transpose()
df_trans2.columns = ['source','sink','linemva','linesus']
df_paths = pd.concat([df_trans1,df_trans2], axis=0)
df_paths.index = np.arange(len(df_paths))


######=================================================########
######               Segment A.3                       ########
######=================================================########

####======== Lists of Nodes of the Power System ========########
h_nodes = ['TTYh','LRCh','ATYh','KIR1h','KIR3h','KMCh']
h_imports = ['Salabam']
##s_nodes = ['solar1','solar2']
##w_nodes =['wind1','wind2']

gd_nodes = ['GS1','GS2','GS3','GS5','GS7','KPCM','KPT','SHV','SRP'] ##Thermoplant nodes with demand
gn_nodes = ['STH','Thai','Viet'] ##Thermoplants nodes without demand

g_nodes = gd_nodes + gn_nodes
print ('Gen_Nodes:',len(g_nodes))

td_nodes = ['GS4','GS6','BTB','BMC','STR','TKO','KPS'] ##Transformers with demand
tn_nodes = ['IE','KPCG','OSM','PRST'] ##Transformers without demand

d_nodes = gd_nodes + td_nodes
print ('Demand_Nodes:',len(d_nodes))

all_nodes = h_nodes + h_imports + gn_nodes + gd_nodes + tn_nodes + td_nodes ## + s_nodes + w_nodes
print ('Total_Nodes:',len(all_nodes))


##list of types of dispatchable units
types = ['coal_st','oil_ic','oil_st','imp_viet','imp_thai','slack'] ##,'biomass_st','gas_cc','gas_st'


######=================================================########
######               Segment A.4                       ########
######=================================================########

######====== write data.dat file ======########
with open(''+str(data_name)+'.dat', 'w') as f:

###### generator sets by generator nodes
    for z in gd_nodes:
        # node string
        z_int = gd_nodes.index(z)
        f.write('set GD%dGens :=\n' % (z_int+1))
        # pull relevant generators
        for gen in range(0,len(df_gen)):
            if df_gen.loc[gen,'node'] == z:
                unit_name = df_gen.loc[gen,'name']
                unit_name = unit_name.replace(' ','_')
                f.write(unit_name + ' ')
        f.write(';\n\n')    
    
    for z in gn_nodes:
        # node string
        z_int = gn_nodes.index(z)
        f.write('set GN%dGens :=\n' % (z_int+1))
        # pull relevant generators
        for gen in range(0,len(df_gen)):
            if df_gen.loc[gen,'node'] == z:
                unit_name = df_gen.loc[gen,'name']
                unit_name = unit_name.replace(' ','_')
                f.write(unit_name + ' ')
        f.write(';\n\n')    

    
####### generator sets by type  
    # Coal
    f.write('set Coal_st :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'coal_st':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')        

    # Oil_ic
    f.write('set Oil_ic :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'oil_ic':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')  

    # Oil_st
    f.write('set Oil_st :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'oil_st':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')  

    # Import from Vietnam
    f.write('set Imp_Viet :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'imp_viet':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')

    # Import from Thailand
    f.write('set Imp_Thai :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'imp_thai':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')

##    # Biomass
##    f.write('set Biomass_st :=\n')
##    # pull relevant generators
##    for gen in range(0,len(df_gen)):
##        if df_gen.loc[gen,'typ'] == 'biomass_st':
##            unit_name = df_gen.loc[gen,'name']
##            unit_name = unit_name.replace(' ','_')
##            f.write(unit_name + ' ')
##    f.write(';\n\n')    
##
##    # Gas_cc
##    f.write('set Gas_cc :=\n')
##    # pull relevant generators
##    for gen in range(0,len(df_gen)):
##        if df_gen.loc[gen,'typ'] == 'gas_cc':
##            unit_name = df_gen.loc[gen,'name']
##            unit_name = unit_name.replace(' ','_')
##            f.write(unit_name + ' ')
##    f.write(';\n\n')  
##
##    # Gas_st
##    f.write('set Gas_st :=\n')
##    # pull relevant generators
##    for gen in range(0,len(df_gen)):
##        if df_gen.loc[gen,'typ'] == 'gas_st':
##            unit_name = df_gen.loc[gen,'name']
##            unit_name = unit_name.replace(' ','_')
##            f.write(unit_name + ' ')
##    f.write(';\n\n')

    # Slack
    f.write('set Slack :=\n')
    # pull relevant generators
    for gen in range(0,len(df_gen)):
        if df_gen.loc[gen,'typ'] == 'slack':
            unit_name = df_gen.loc[gen,'name']
            unit_name = unit_name.replace(' ','_')
            f.write(unit_name + ' ')
    f.write(';\n\n')  


######=================================================########
######               Segment A.5                       ########
######=================================================########

######Set nodes, sources and sinks
    # nodes
    f.write('set nodes :=\n')
    for z in all_nodes:
        f.write(z + ' ')
    f.write(';\n\n')
    
    # sources
    f.write('set sources :=\n')
    for z in all_nodes:
        f.write(z + ' ')
    f.write(';\n\n')
    
    # sinks
    f.write('set sinks :=\n')
    for z in all_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # hydro_nodes
    f.write('set h_nodes :=\n')
    for z in h_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # hydro_nodes for import
    f.write('set h_imports :=\n')
    for z in h_imports:
        f.write(z + ' ')
    f.write(';\n\n')

##    # solar_nodes
##    f.write('set s_nodes :=\n')
##    for z in s_nodes:
##        f.write(z + ' ')
##    f.write(';\n\n')
##
##    # wind_nodes
##    f.write('set w_nodes :=\n')
##    for z in w_nodes:
##        f.write(z + ' ')
##    f.write(';\n\n')

    # all demand nodes
    f.write('set d_nodes :=\n')
    for z in d_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # generator with demand nodes
    f.write('set gd_nodes :=\n')
    for z in gd_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # generator without demand nodes
    f.write('set gn_nodes :=\n')
    for z in gn_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # transformer with demand nodes
    f.write('set td_nodes :=\n')
    for z in td_nodes:
        f.write(z + ' ')
    f.write(';\n\n')

    # transformer without demand nodes
    f.write('set tn_nodes :=\n')
    for z in tn_nodes:
        f.write(z + ' ')
    f.write(';\n\n')


######=================================================########
######               Segment A.6                       ########
######=================================================########
       
####### simulation period and horizon
    f.write('param SimHours := %d;' % SimHours)
    f.write('\n')
    f.write('param SimDays:= %d;' % SimDays)
    f.write('\n\n')   
    f.write('param HorizonHours := %d;' % HorizonHours)
    f.write('\n\n')
    f.write('param TransLoss := %0.3f;' % TransLoss)
    f.write('\n\n')
    f.write('param n1criterion := %0.3f;' % n1criterion)
    f.write('\n\n')
    f.write('param spin_margin := %0.3f;' % spin_margin)
    f.write('\n\n')


######=================================================########
######               Segment A.7                       ########
######=================================================########
    
####### create parameter matrix for generators
    f.write('param:' + '\t')
    for c in df_gen.columns:
        if c != 'name':
            f.write(c + '\t')
    f.write(':=\n\n')
    for i in range(0,len(df_gen)):    
        for c in df_gen.columns:
            if c == 'name':
                unit_name = df_gen.loc[i,'name']
                unit_name = unit_name.replace(' ','_')
                f.write(unit_name + '\t')  
            else:
                f.write(str((df_gen.loc[i,c])) + '\t')               
        f.write('\n')
    f.write(';\n\n')     

######=================================================########
######               Segment A.8                       ########
######=================================================########

####### create parameter matrix for transmission paths (source and sink connections)
    f.write('param:' + '\t' + 'linemva' + '\t' +'linesus :=' + '\n')
    for z in all_nodes:
        for x in all_nodes:           
            f.write(z + '\t' + x + '\t')
            match = 0
            for p in range(0,len(df_paths)):
                source = df_paths.loc[p,'source']
                sink = df_paths.loc[p,'sink']
                if source == z and sink == x:
                    match = 1
                    p_match = p
            if match > 0:
                f.write(str(df_paths.loc[p_match,'linemva']) + '\t' + str(df_paths.loc[p_match,'linesus']) + '\n')
            else:
                f.write('0' + '\t' + '0' + '\n')
    f.write(';\n\n')

######=================================================########
######               Segment A.9                       ########
######=================================================########

####### Hourly timeseries (load, hydro, solar, wind, reserve)
    # load (hourly)
    f.write('param:' + '\t' + 'SimDemand:=' + '\n')      
    for z in d_nodes:
        for h in range(0,len(df_load)): 
            f.write(z + '\t' + str(h+1) + '\t' + str(df_load.loc[h,z]) + '\n')
    f.write(';\n\n')

    # hydro (hourly)
    f.write('param:' + '\t' + 'SimHydro:=' + '\n')      
    for z in h_nodes:
        for h in range(0,len(df_hydro)): 
            f.write(z + '\t' + str(h+1) + '\t' + str(df_hydro.loc[h,z]) + '\n')
    f.write(';\n\n')

    # hydro_import (hourly)
    f.write('param:' + '\t' + 'SimHydroImport:=' + '\n')      
    for z in h_imports:
        for h in range(0,len(df_hydro_import)): 
            f.write(z + '\t' + str(h+1) + '\t' + str(df_hydro_import.loc[h,z]) + '\n')
    f.write(';\n\n')

##    # solar (hourly)
##    f.write('param:' + '\t' + 'SimSolar:=' + '\n')      
##    for z in s_nodes:
##        for h in range(0,len(df_solar)): 
##            f.write(z + '\t' + str(h+1) + '\t' + str(df_solar.loc[h,z]) + '\n')
##    f.write(';\n\n')
##
##    # wind (hourly)
##    f.write('param:' + '\t' + 'SimWind:=' + '\n')      
##    for z in w_nodes:
##        for h in range(0,len(df_wind)): 
##            f.write(z + '\t' + str(h+1) + '\t' + str(df_wind.loc[h,z]) + '\n')
##    f.write(';\n\n')
    
###### System-wide hourly reserve
    f.write('param' + '\t' + 'SimReserves:=' + '\n')
    for h in range(0,len(df_load)):
            f.write(str(h+1) + '\t' + str(df_reserves.loc[h,'Reserve']) + '\n')
    f.write(';\n\n')
    

print ('Complete:',data_name)
