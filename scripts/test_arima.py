import os
from pownet.stochastic.solar import SolarTSModel
from pownet.stochastic.demand import DemandTSModel
import pandas as pd
import matplotlib.pyplot as plt

import logging

# Show info
logging.basicConfig(level=logging.INFO)

# %% Demand

data = pd.read_csv("../temp/hourly_demand_2023.csv")

demand_model = DemandTSModel()
demand_model.load_data(data)
exog_vars = ["temp", "rhum", "prcp", "weekend"]

# arima_order, seasonal_order = demand_model.find_best_model(
#     target_column="demand",
#     exog_vars=exog_vars,
# )


demand_model.fit(
    target_column="demand",
    exog_vars=exog_vars,
    arima_order=(1, 0, 1),
    seasonal_order=(0, 0, 0, 0),
)
predictions = demand_model.predict()

data.index = pd.to_datetime(data["datetime"])
exog_data = data[exog_vars].astype(float)
synthetic = demand_model.get_synthetic(exog_data=exog_data)


duration = 10
# plt.plot(predictions[: 24 * 3], label="Predictions")
plt.plot(synthetic[: 24 * duration], label="Synthetic")
plt.plot(
    data.set_index("datetime")["demand"].iloc[: 24 * duration],
    label="Actual",
)
plt.legend()
plt.show()

"""# %% Solar
data = pd.read_csv("../temp/merra_2019.csv")

solar_model = SolarTSModel()
solar_model.load_data(data)

solar_model.fit(target_column="ground_irradiance", arima_order=(2, 1, 2))
predictions = solar_model.predict()

resids = solar_model.pred_residuals"""

# synthetic = solar_model.get_synthetic()

# duration = 30
# # plt.plot(predictions[: 24 * 3], label="Predictions")
# plt.plot(synthetic[: 24 * duration], label="Synthetic")
# plt.plot(
#     data.set_index("datetime")["ground_irradiance"].iloc[: 24 * duration],
#     label="Actual",
# )
# plt.legend()
# plt.show()
