""" kirsch_nowak.py
"""

import numpy as np
from scipy.linalg import cholesky, eig


def KNN_identification(Z, Qtotals, month, k=None):
    """
    Identifies K-nearest neighbors of Z in the historical annual data
    and computes the associated weights W.

    Args:
        Z: Synthetic datum (scalar)
        Qtotals: Total monthly flows at all sites for all historical months
                 within +/- 7 days of the month being disaggregated
        month: Month being disaggregated
        k: Number of nearest neighbors (by default k=n_year^0.5
           according to Lall and Sharma (1996))


    Returns:
        KNN_id: Indices of the first K-nearest neighbors of Z in the
                historical annual data z
        W: Nearest neighbors weights, according to Lall and Sharma (1996):
           W(i) = (1/i) / (sum(1/i))
    """

    # Ntotals is the number of historical monthly patterns used for disaggregation.

    Ntotals = Qtotals[month].shape[0]

    if k is None:
        K = round(np.sqrt(Ntotals))
    else:
        K = k

    # Nearest neighbors identification
    Nsites = Qtotals[month].shape[1]
    delta = np.zeros(Ntotals)

    for i in range(Ntotals):
        for j in range(Nsites):
            delta[i] += (Qtotals[month][i, j] - Z[0, 0, j]) ** 2

    Y = np.column_stack((np.arange(1, Ntotals + 1), delta))
    Y_ord = Y[Y[:, 1].argsort()]  # Sort by the second column (delta)
    KNN_id = Y_ord[:K, 0].astype(int)  # Extract the first column (indices)

    # Computation of the weights
    f = np.arange(1, K + 1)
    f1 = 1 / f
    W = f1 / np.sum(f1)

    return KNN_id, W


def chol_corr(Z):
    """
    Computes the Cholesky decomposition of the correlation matrix of the columns of Z.
    Attempts to repair non-positive-definite matrices.
    """

    R = np.corrcoef(Z, rowvar=False)  # Calculate the correlation matrix
    U, p = cholesky(R, lower=False)  # Attempt Cholesky decomposition

    while p > 0:  # If not positive definite, modify slightly
        k = min(
            [np.min(np.real(eig(R)[0])) - 1e-15, -1e-15]
        )  # Smallest eigenvalue or a small negative value
        R = R - k * np.eye(R.shape[0])
        R = R / R[0, 0]  # Rescale to get unit diagonal entries
        U, p = cholesky(R, lower=False)  # Retry Cholesky decomposition

    return U
