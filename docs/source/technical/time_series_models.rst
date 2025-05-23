
.. autosummary::
    :toctree: _source/
    
**Time series modeling**
=========================

**ARIMA Model**

ARIMA (Autoregressive Integrated Moving Average) is a foundational time-series modeling technique that combines three components:

    * Autoregression (:math:`AR(p)`): Models the value at time t as a linear function of its own p lagged values, capturing persistence and momentum in the series.
    * Integration (:math:`I(d)`): Applies differencing of order d to remove trends and achieve stationarity, ensuring the series has constant mean and variance over time.
    * Moving Average (:math:`MA(q)`): Represents the value at time t as a linear function of q past forecast errors, capturing short-term shocks and noise.

**SARIMAX Model**

SARIMAX (Seasonal Autoregressive Integrated Moving Average with eXogenous regressors) extends the classic ARIMA framework by explicitly modeling both seasonality and the influence of external variables on the series. In SARIMAX, the observed series :math:`y_t` is first differenced :math:`d` times to achieve stationarity, similar to ARIMA; the residual structure is then captured by:

    * Seasonality: Additional differencing and seasonal AR/MA terms at lag :math:`s` (period) to model repeating patterns (e.g., daily, weekly), by seasonally differencing :math:`D` times with period :math:`s`
    * Exogenous Regressors: Incorporates external variables (e.g., temperature, calendar indicators) linearly to explain known drivers of variability.

**Monthly SARIMAX Model**

We employ a per-month SARIMAX model for:

    * Non‑Stationary Seasonality across the Year: Daily/weekly cycle shapes (peak sharpness, trough depth) change with season.
    * Localized Parameter Tuning: Fitting separate SARIMAX for each calendar month allows tailored (p,d,q)(P,D,Q,s) orders per month.
    * Improved Forecast Robustness: Month‑specific models reduce over‑ or under‑differencing risk and avoid a one‑size‑fits‑all seasonal period.

**Demand Model**

In short‑term load forecasting, SARIMAX is well suited because demand exhibits strong intra‑day/weekly cycles plus dependencies on weather and calendar effects. We equip the model with the ability to forecase the hourly electricity demand:

    * **Step 1:** We first run an ordinary least squares (OLS) regression on user-supplied exogenous variables (such as temperature) and get the residual series. The OLS isolates the “explained” portion of demand and the residual is treated as a stationary series for further time‐series modeling.
    * **Step 2:** We run a Seasonal-Trend decomposition using LOESS (STL) to decompose a time series into three components: trend, season(al) and residual. 
    * **Step 3:** We fit a Seasonal Autoregressive Integrated Moving Average with Exogenous Regressors (SARIMAX) model to capture the correlation structure, and store per-month SARIMAX models and residuals.

We run auto-ARIMA on the detrended, deseasonalized residuals to pick (p,d,q)(P,D,Q,s) orders that best capture autocorrelation left after regression + STL. We can then get synthetic time series by comnbining regression, drawing sample paths from each monthly SARIMAX, and adding seasonal and trend components.

**Solar Model**

Solar generation follows a deterministic diurnal "bell curve" and seasonal envelope, with high‑frequency fluctuations due to clouds and atmosphere, therefore we can also use SARIMAX to capture stochastic variability. Similarly, we would like to forecase solar irradiance/PV output. We follow a similar structure to the demand model, but:

    * No pre-regression on exogenous weather, instead, the STL decomposition itself captures the deterministic daily/seasonal envelope and all remaining variation feeds directly into SARIMAX.
    * Clip output to nonnegative and force it to zero during night hours.

**Related Works**

SARIMAX is a tried-and-tested way of modeling both demand and solar irradiance as demonstrated by the following works:

    * N. Elamin, M. Fukushige. Modeling and forecasting hourly electricity demand by SARIMAX with interactions. *Energy*. Volume 165, Part B, 2018, Pages 257-268, ISSN 0360-5442.
    * E. Eskandarnia and M. AlHammad, "Predication of future energy consumption using SARIMAX," *3rd Smart Cities Symposium (SCS 2020)*, 2020, pp. 657-662.
    * S. Vagropoulos, G. Chouliaras, E. Kardakos, C. Simoglou and A. Bakirtzis, "Comparison of SARIMAX, SARIMA, modified SARIMA and ANN-based models for short-term PV generation forecasting," *2016 IEEE International Energy Conference (ENERGYCON)*, Leuven, Belgium, 2016, pp. 1-6.