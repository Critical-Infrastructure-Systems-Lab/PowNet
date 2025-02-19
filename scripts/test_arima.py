from pownet.stochastic.solar import SolarTSModel
import pandas as pd
import matplotlib.pyplot as plt

from pownet.data_utils import get_datetime_index

import logging

# Show info
logging.basicConfig(level=logging.INFO)

# %% Solar
data = pd.read_csv("../temp/merra_2019.csv")
data["datetime"] = pd.to_datetime(data["datetime"])

solar_model = SolarTSModel()
solar_model.load_data(data)

solar_model.fit(target_column="ground_irradiance", arima_order=(2, 1, 2))
predictions = solar_model.predict()
predictions.head(20)

resids = solar_model.pred_residuals

synthetic = solar_model.get_synthetic()

duration = 30
# plt.plot(predictions[: 24 * 3], label="Predictions")
plt.plot(synthetic[: 24 * duration], label="Synthetic")
plt.plot(
    data.set_index("datetime")["ground_irradiance"].iloc[: 24 * duration],
    label="Actual",
)
plt.legend()
plt.show()
