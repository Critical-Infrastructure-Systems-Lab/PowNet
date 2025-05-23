
.. autosummary::
    :toctree: _source/
    
**Linearized DC power flow**
================================

**Overview**

In alternating‐current (AC) power systems, power is transmitted at high voltages through a network of buses and transmission lines and is a crucial part of an energy system. Each line can be characterized by its series impedance (resistance and reactance). We model power flow in a by both voltage magnitudes and angles at its ends, as described by the nonlinear AC power flow equation for real power:

    :math:`P_{ij}=V_i V_j(G_{ij}\cos{(\theta_i-\theta_j)} + B_{ij}\sin{(\theta_i-\theta_j)})-V_i^2G_{ij}`

where :math:`V_i` is the voltage magnitude at bus :math:`i`, :math:`\theta_i` is the voltage angle, :math:`G_{ij}` and :math:`B_{ij}` are the conductance (1 over resistance) and susceptance (1 over reactance) of the line between bus :math:`i` and bus :math:`j`.

The full AC equation above captures the full dynamics but is nonlinear due to the trigonometric terms and quadratic dependence on voltage magnitudes. To simplify analysis and enable efficient optimization, we use a DC power flow approximation based on:
    
    * **Negligible Resistance**: Line losses due to resistance are assumed small compared to reactance for high-voltage large-scale power grids, so resistances are ignored and only reactances remain.
    * **Small Angle Differences**: Voltage angle differences are small enough that :math:`\sin{(\theta_i)}` approaches :math:`\theta_i`.

therefore we simplify the real power flow on a line as follows:

    :math:`P_{ij}=B_{ij}(\theta_i-\theta_j)`

where :math:`P_{ij}` is the powerflow in a line, :math:`B_{ij}` is the line susceptance, and :math:`\theta_i` the voltage angle.

**Model**

The above formulation translates into the following in our model: 

    * Decision Variables:Our decision variables therefore include :math:`\theta_i` for each bus :math:`i`, representing the phase angle; line flows :math:`F_{ij}` as auxiliary variables representing the real power on each line. 
    * Parameters:Constant :math:`B_{ij}` representing the line susceptance between bus :math:`i` and :math:`j`.
    * Flow: DC approcimation of power flow.
        :math:`F_{ij}=B_{ij}(\theta_i-\theta_j)`
    * Kirchoff's Current Law: Power Balance at each bus. :math:`P_i^{gen} - P_i^{load}` represents the net power injection (generation minus loads) at bus :math:`i`.
        :math:`P_i^{gen} - P_i^{load} = \sum F_{ij} -  \sum F_{ji}`
    * Line Capacity Constraint:
        :math:`-F_{ij}^{max} \le F_{ij} \le F_{ij}^{max}`

By combining these elements: angle and flow variables, a linear flow, nodal balance equations, and capacity bounds, our code realizes the classic DC power flow model entirely within a (mixed integer) linear framework.