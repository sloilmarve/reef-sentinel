# -*- coding: utf-8 -*-
"""The single model of this project, and the protocol around it.

Ridge regression solved in closed form (normal equations, intercept unpenalised) - no
gradient descent, no persisted weights, no sklearn: every refresh refits from the record
it has, and a different site simply rebuilds its own thresholds and coefficients.

The regularisation strength is NOT a hand-picked constant.  Inside each walk-forward
training window only, the window is split again in time order (first 70% fit, next 15%
score, then first 85% fit, last 15% score) and the lambda with the best mean inner score
is carried to the test window.  The test window is never used to pick lambda.
"""
import numpy as np

LAMBDA_GRID = (5.0, 20.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0)
INNER_CUTS = (0.70, 0.85)

def matrix(days, keys):
    return np.array([[float(r.get(k)) if r.get(k) is not None else np.nan for k in keys]
                     for r in days], dtype=float)

def ridge_fit(Xtr, ytr, lam):
    mu = np.nanmean(Xtr, 0); mu = np.where(np.isnan(mu), 0, mu)
    Z = np.where(np.isnan(Xtr), mu, Xtr)
    sd = Z.std(0); sd[sd == 0] = 1; Z = (Z - mu) / sd
    Zb = np.hstack([np.ones((len(Z), 1)), Z])
    A = Zb.T @ Zb + lam * np.eye(Zb.shape[1]); A[0, 0] -= lam
    return np.linalg.solve(A, Zb.T @ ytr), mu, sd

def ridge_pred(w, mu, sd, Xa):
    Z = np.where(np.isnan(Xa), mu, Xa); Z = (Z - mu) / sd
    return np.hstack([np.ones((len(Z), 1)), Z]) @ w

def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))

def auc(p, l):
    """Mann-Whitney rank-sum AUC (no scipy)."""
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    npos = float((l == 1).sum()); nneg = len(p) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    return float((r[l == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))

def inner_lambda(Xtr, ytr, grid=LAMBDA_GRID, cuts=INNER_CUTS):
    """Pick lambda on the training window only, using two time-ordered inner splits."""
    m = len(ytr); a = int(m * cuts[0]); b = int(m * cuts[1])
    best, bl = None, None
    for lam in grid:
        errs = []
        for cut, end in ((a, b), (b, m)):
            w, mu, sd = ridge_fit(Xtr[:cut], ytr[:cut], lam)
            errs.append(rmse(ridge_pred(w, mu, sd, Xtr[cut:end]), ytr[cut:end]))
        v = float(np.mean(errs))
        if best is None or v < best:
            best, bl = v, lam
    return bl