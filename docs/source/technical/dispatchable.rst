
.. autosummary::
    :toctree: _source/
    
**Dispatchable/Non-dispatchable generators**
===============================================

**Overview**

Electric power systems rely on a mix of generation technologies. Broadly, these fall into two categories:
    * Dispatchable generators: Facilities whose output can be adjusted up or down by the system operator (e.g., natural gas, coal), subject to physical limits (ramping limits, minimum up/down times).
    * Non‑dispatchable generators: Units that produce energy according to an exogenous resource profile (e.g., wind turbines, solar PV), with limited or no ability for the operator to increase output beyond what nature provides.

**Dispatchable generators**

We model the operation of dispatchable generators using three variables:
    
    * Dispatch variable :math:`p_{g,t}`: Power output of generator :math:`g` at time :math:`t`. More specifically, it is split into "above-min" generation :math:`p'_{g,t}` and "at-min" generation :math:`\underline{P}_g`
    * Commitment variable :math:`u_{g,t} \in \{0,1\}`: Binary indicator if :math:`g` is online.
    * Starting/Shutdown variable :math:`v_{g,t}, w_{g,t} \in \{0,1\}`: Binary indicator if :math:`g` is starting up or shutting down at time :math:`t`.

Each dispatchable generator is subject to constraints:
    
    * Capacity: The capacity is constrainted by the minimum and maximum capacity.
        :math:`\underline{P}_g \times u_{g,t} \le P'_{g,t} + \underline{P}_g \le \bar{P}_g \times u_{g,t}`
    
    * Ramping limit: The change in power output from :math:`t` to :math:`t+1` cannot be over the ramping limit. 
    * Minimum up/down time: Once started or stopped, the unit remains in that state for the specified duration.
    * Must take: If the unit has to be included in the generation profile.

We then minimize the cost of generation, for which the cost of individual dispatchable generator is given by:
    
    * Fixed cost: Fixed cost is a function of rated capacity and fixed cost per unit.
        :math:`c_{g,t}^{fixed} = \bar{P}_g \times {fixed\_cost\_per\_unit}_g \times u_{g,t}`
    
    * Variable cost: Variable cost is a function of fuel cost, heat rate, and operating cost.
        :math:`c_{g,t}^{var} = (({fuel\_price}_g \times {heat\_rate}_g) + {opex}_g) \times p_{g,t}`
    
    * Startup cost: Startup cost is a function of rated capacity and startup cost per unit.
        :math:`c_{g,t}^{start} = P_g^{max} \times {startup\_cost}_g \times v_{g,t}`

    * Curtailment cost: Curtailing "must-take" thermal output is priced as the same variable rate.
        :math:`c_{g,t}^{curt} = (({fuel\_price}_g \times {heat\_rate}_g) + {opex}_g) \times p^curt_{g,t}`

**Non-dispatchable generators**

For non-dispatchable generators, the model's decision is to dispatch, curtail, or store the renewable energy produced. We therefore have:
    
    * Dispatched :math:`pdispatch_{g,t}`
    * Curtailed :math:`pcurtail_{g,t}`
    * Charged :math:`pcharge_{g,t}`

Non-dispatchable generators are subject to constraints:
    
    * Available capacity:
        :math:`pdispatch_{g,t} \le available\_capacity_{g,t}`
    * Energy balance:
        :math:`pdispatch_{g,t} + pcurtail_{g,t} + pcharge_{g,t} = available\_capacity_{g,t}`

We assume non-dispatchable generators do not have a fixed or start-up cost, and we get the variable cost from the contract price:
    
    * Variable cost:
        :math:`c_{g,t}^{var} = {contract\_price}_g \times pdispatch_{g,t}`