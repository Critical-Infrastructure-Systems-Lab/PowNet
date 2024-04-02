class Reoperator:
    ''' This class compares the hydropower dispatch with hydropower availability.
    If the hydropower dispatch is less than the hydropower availability, then
    it updates new hydropower capacity in Input class.
    '''

    def __init__(self, hydro_dispatch, hydro_cap):
        self.hydro_dispatch = hydro_dispatch
        self.hydro_cap = hydro_cap

    def get_hydro_dispatch(self):
        return self.hydro_dispatch

    def get_hydro_acap(self):
        return self.hydro_cap

    def reoperate(self):
        ''' This method reoperates the reservoirs. '''
        hydro_dispatch = self.get_hydro_dispatch()
        hydro_cap = self.get_hydro_acap()

        # Check if the hydropower was fully used per Koh et al. (2022)
        for node in hydro_dispatch:
            if hydro_dispatch[node] < hydro_cap[node]:
                hydro_cap[node] = hydro_dispatch[node]
