"""
ClassificationService: the only file allowed to touch gradient_boosting_model.pkl.

Design rule: the ML model is the sole source of truth for the prediction. The
LLM never goes near this step -- feature dict(s) in, label + probabilities out.

FEATURE ORDER SAFETY: passing features to a scikit-learn model in the wrong order
silently produces a wrong (but plausible-looking) prediction. If the loaded model
exposes `feature_names_in_`, it is compared against FEATURE_ORDER at load time and
predictions are refused on a mismatch.

Features are passed as a pandas DataFrame with named columns (the model was
fitted on a DataFrame), which avoids scikit-learn's "X does not have valid
feature names" warning on every request. If pandas is unavailable, a plain
list-of-lists in FEATURE_ORDER is used instead.

predict_many() classifies N objects in ONE model call (used by batch analysis).
"""
import os
import warnings
from typing import Any, Dict, List, Optional

from app.utils.config import settings

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PANDAS_AVAILABLE = False

# Exact feature name/order the model was trained on (confirmed against the
# model's own feature_names_in_). Matches tle_service.extract_orbital_parameters()
# output keys exactly -- no renaming needed.
FEATURE_ORDER: List[str] = [
    "inclination_deg", "eccentricity", "raan_deg", "arg_perigee_deg",
    "mean_anomaly_deg", "mean_motion_rev_per_day", "semi_major_axis_km",
    "altitude_km", "orbital_velocity_km_s", "orbital_period_min",
    "specific_orbital_energy_km2_s2",
]

LABEL_NAMES = {0: "ACTIVE SATELLITE", 1: "SPACE DEBRIS"}
MODEL_DISPLAY_NAME = "Gradient Boosting Classifier"


class ModelNotFoundError(Exception):
    pass


class ModelLoadError(Exception):
    pass


class FeatureOrderMismatchError(Exception):
    pass


class ClassificationService:
    def __init__(self, model_path: Optional[str] = None, model: Any = None):
        """`model` can be injected directly (tests use a mock). The feature-order
        check runs either way."""
        self.model_path = model_path or settings.classification_model_path
        self._model: Any = None
        self._load_error: Optional[str] = None
        if model is not None:
            self._validate_and_set(model)
        else:
            self._load()

    # ---------------------------------------------------------------- loading --
    def _load(self) -> None:
        if not os.path.exists(self.model_path):
            self._load_error = (
                f"Classification model not found at '{self.model_path}'. Set "
                "CLASSIFICATION_MODEL_PATH in .env to point at your trained "
                "gradient_boosting_model.pkl."
            )
            return
        try:
            from joblib import load
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = load(self.model_path)
            version_warnings = [w for w in caught
                                if "InconsistentVersionWarning" in type(w.message).__name__]
            if version_warnings:
                trained = getattr(version_warnings[0].message, "original_sklearn_version", "?")
                current = getattr(version_warnings[0].message, "current_sklearn_version", "?")
                print(f"[ClassificationService] WARNING: model was saved with scikit-learn {trained} "
                      f"but {current} is installed. Run: pip install scikit-learn=={trained}")
        except Exception as e:
            self._load_error = f"Failed to load classification model from '{self.model_path}': {e}"
            return
        self._validate_and_set(model)

    def _validate_and_set(self, model: Any) -> None:
        mismatch = self._check_feature_order(model)
        if mismatch:
            self._load_error = mismatch
            return
        self._model = model

    @staticmethod
    def _check_feature_order(model: Any) -> Optional[str]:
        names = getattr(model, "feature_names_in_", None)
        if names is None:
            return None  # model wasn't trained on a DataFrame -- nothing to check
        model_order = list(names)
        if model_order != FEATURE_ORDER:
            return (
                "Feature order mismatch between this service's FEATURE_ORDER and the "
                f"loaded model's feature_names_in_.\n  Expected: {FEATURE_ORDER}\n"
                f"  Model was trained on: {model_order}\n"
                "Update FEATURE_ORDER in classification_service.py to match the model "
                "exactly before trusting any prediction from it."
            )
        return None

    # ------------------------------------------------------------------ status --
    def is_ready(self) -> bool:
        return self._model is not None

    def load_error(self) -> Optional[str]:
        return self._load_error

    def model_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {"ready": self.is_ready(), "error": self._load_error}
        if self._model is not None:
            info["type"] = type(self._model).__name__
        return info

    # --------------------------------------------------------------- predicting --
    def _to_matrix(self, rows: List[Dict[str, float]]):
        values = [[float(r[name]) for name in FEATURE_ORDER] for r in rows]
        if _PANDAS_AVAILABLE and getattr(self._model, "feature_names_in_", None) is not None:
            return pd.DataFrame(values, columns=FEATURE_ORDER)
        return values

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        return self.predict_many([features])[0]

    def predict_many(self, feature_rows: List[Dict[str, float]]) -> List[Dict[str, Any]]:
        """Classifies every row in ONE model call. Raises on a missing model or
        missing features (callers turn that into a clean error)."""
        if not self.is_ready():
            raise ModelNotFoundError(self._load_error or "Classification model is not loaded.")
        if not feature_rows:
            return []
        for i, row in enumerate(feature_rows):
            missing = [f for f in FEATURE_ORDER if f not in row or row[f] is None]
            if missing:
                raise ValueError(f"Missing required feature(s) for classification (row {i}): {missing}")

        X = self._to_matrix(feature_rows)
        try:
            labels = self._model.predict(X)
            probas = self._model.predict_proba(X)
        except Exception as e:
            raise RuntimeError(f"Model prediction failed: {e}")

        classes = [int(c) for c in getattr(self._model, "classes_", [0, 1])]
        idx_sat = classes.index(0) if 0 in classes else 0
        idx_deb = classes.index(1) if 1 in classes else 1

        results = []
        for label, proba in zip(labels, probas):
            label = int(label)
            satellite_pct = round(float(proba[idx_sat]) * 100, 2)
            debris_pct = round(float(proba[idx_deb]) * 100, 2)
            results.append({
                "label": label,
                "prediction": LABEL_NAMES.get(label, f"UNKNOWN ({label})"),
                "confidence": debris_pct if label == 1 else satellite_pct,
                "probabilities": {"satellite": satellite_pct, "debris": debris_pct},
            })
        return results

