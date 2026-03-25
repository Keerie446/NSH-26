"""NSH 2026 — ML Models: XGBoost + LSTM for collision prediction & trajectory correction"""
import numpy as np
import logging
import joblib
import os
from datetime import datetime
from typing import Tuple, List

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger("acm.ml")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
XGBOOST_PATH = os.path.join(MODEL_DIR, "collision_prob_xgboost.pkl")
LSTM_PATH = os.path.join(MODEL_DIR, "trajectory_lstm.pkl")

# ─── XGBoost: Collision Probability Prediction ────────────────────────────────

class CollisionProbabilityModel:
    """
    XGBoost model predicting collision probability.
    
    Features:
        - miss_distance_km: Current closest approach distance
        - relative_velocity_km_s: Relative speed between sat and debris
        - fuel_level_fraction: Satellite fuel remaining (0-1)
        - approach_angle_deg: Angle of approach vector
    """
    
    def __init__(self):
        self.model = None
        self.scaler_mean = np.array([0.5, 7.0, 0.6, 45.0])  # Feature means for normalization
        self.scaler_std = np.array([0.8, 3.0, 0.25, 60.0])   # Feature stds
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize XGBoost model with pre-trained weights or create fresh."""
        if XGBOOST_AVAILABLE:
            try:
                if os.path.exists(XGBOOST_PATH):
                    self.model = joblib.load(XGBOOST_PATH)
                    logger.info("Loaded XGBoost collision probability model from disk")
                else:
                    self._create_default_model()
            except Exception as e:
                logger.warning(f"Failed to load XGBoost: {e}. Creating default model...")
                self._create_default_model()
        else:
            self._create_default_model()
    
    def _create_default_model(self):
        """Create a default model with heuristic weights."""
        if XGBOOST_AVAILABLE:
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
            # Train on synthetic data for demo
            X_train = self._generate_synthetic_data(200)
            y_train = self._label_synthetic_data(X_train)
            self.model.fit(X_train, y_train)
            logger.info("Created and trained default XGBoost model")
        else:
            logger.warning("XGBoost not available, using fallback probability model")
    
    def _generate_synthetic_data(self, n_samples=200):
        """Generate synthetic training data."""
        np.random.seed(42)
        return np.random.randn(n_samples, 4) * self.scaler_std + self.scaler_mean
    
    def _label_synthetic_data(self, X):
        """Label synthetic data: high risk if (miss_dist < 0.2km AND rel_vel > 5) OR (miss_dist < 0.1km)."""
        high_risk = ((X[:, 0] < 0.2) & (X[:, 1] > 5.0)) | (X[:, 0] < 0.1)
        return high_risk.astype(int)
    
    def predict_probability(self, miss_dist_km: float, rel_velocity_km_s: float, 
                           fuel_fraction: float, approach_angle_deg: float) -> float:
        """
        Predict collision probability [0, 1].
        
        Args:
            miss_dist_km: Distance at closest approach (km)
            rel_velocity_km_s: Relative velocity (km/s)
            fuel_fraction: Fuel remaining / initial fuel
            approach_angle_deg: Approach angle (degrees)
        
        Returns:
            Probability of collision [0, 1]
        """
        X = np.array([[miss_dist_km, rel_velocity_km_s, fuel_fraction, approach_angle_deg]])
        
        # Normalize
        X_normalized = (X - self.scaler_mean) / self.scaler_std
        
        if self.model is not None and XGBOOST_AVAILABLE:
            try:
                prob = float(self.model.predict_proba(X_normalized)[0, 1])
                return np.clip(prob, 0.0, 1.0)
            except Exception as e:
                logger.warning(f"XGBoost prediction failed: {e}, using fallback")
        
        # Fallback: simple heuristic
        return self._heuristic_probability(miss_dist_km, rel_velocity_km_s)
    
    def _heuristic_probability(self, miss_dist_km: float, rel_velocity_km_s: float) -> float:
        """Fallback probability using simple heuristics."""
        # Risk increases as miss distance decreases and velocity increases
        dist_risk = np.exp(-max(0, miss_dist_km) / 0.15)  # Sharp increase below 0.15 km
        vel_risk = min(1.0, rel_velocity_km_s / 12.0)  # Saturating velocity risk at 12 km/s
        return np.clip(0.4 * dist_risk + 0.6 * vel_risk, 0.0, 1.0)


# ─── LSTM: Trajectory Correction Prediction ────────────────────────────────────

class TrajectoryLSTMModel(nn.Module if TORCH_AVAILABLE else object):
    """
    LSTM neural network predicting optimal trajectory correction delta-v.
    
    Input: Sequential state history (6 timesteps x 6 features each)
           Features: [x, y, z, vx, vy, vz] in ECI coordinates
    
    Output: [dv_x, dv_y, dv_z] delta-v correction in km/s
    """
    
    def __init__(self, input_size=6, hidden_size=64, output_size=3, seq_len=6):
        if TORCH_AVAILABLE:
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True, num_layers=2)
            self.fc = nn.Sequential(
                nn.Linear(hidden_size, 32),
                nn.ReLU(),
                nn.Linear(32, output_size)
            )
            self.seq_len = seq_len
        else:
            self.hidden_size = hidden_size
            self.output_size = output_size
            self.seq_len = seq_len
        
        self.model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize or load LSTM weights."""
        if TORCH_AVAILABLE:
            try:
                if os.path.exists(LSTM_PATH):
                    self.load_state_dict(torch.load(LSTM_PATH))
                    logger.info("Loaded LSTM trajectory correction model from disk")
            except Exception as e:
                logger.warning(f"Could not load LSTM: {e}")
    
    def forward(self, x):
        """
        x: (batch_size, seq_len, 6)
        """
        if TORCH_AVAILABLE:
            lstm_out, (h_n, c_n) = self.lstm(x)
            # Use last hidden state
            last_hidden = h_n[-1]  # (batch_size, hidden_size)
            dv = self.fc(last_hidden)  # (batch_size, 3)
            return dv
        return None
    
    def predict_correction(self, state_history: np.ndarray) -> np.ndarray:
        """
        Predict optimal delta-v correction.
        
        Args:
            state_history: (6, 6) array of [x,y,z,vx,vy,vz] over 6 timesteps
        
        Returns:
            dv: (3,) array [dv_x, dv_y, dv_z] in km/s
        """
        if not TORCH_AVAILABLE:
            return self._heuristic_correction(state_history)
        
        try:
            self.eval()
            with torch.no_grad():
                x_tensor = torch.from_numpy(state_history.reshape(1, self.seq_len, 6)).float()
                dv = self.forward(x_tensor).numpy()[0]
            return dv
        except Exception as e:
            logger.warning(f"LSTM prediction failed: {e}, using heuristic")
            return self._heuristic_correction(state_history)
    
    def _heuristic_correction(self, state_history: np.ndarray) -> np.ndarray:
        """Fallback: compute delta-v using simple orbital mechanics."""
        # Use last state (most recent)
        r = state_history[-1, :3]
        v = state_history[-1, 3:]
        
        # Simple tangential correction to lower orbit
        v_mag = np.linalg.norm(v)
        v_direction = v / v_mag
        
        # Small retrograde impulse to slow down
        dv = -0.005 * v_direction  # 5 m/s opposite to velocity
        return dv


# ─── Singleton instances ────────────────────────────────────────────────────────

collision_prob_model = None
trajectory_model = None

def initialize_ml_models():
    """Initialize ML models at startup."""
    global collision_prob_model, trajectory_model
    
    collision_prob_model = CollisionProbabilityModel()
    logger.info("✓ Collision probability (XGBoost) model initialized")
    
    if TORCH_AVAILABLE:
        trajectory_model = TrajectoryLSTMModel()
        logger.info("✓ Trajectory correction (LSTM) model initialized")
    else:
        logger.warning("⚠ PyTorch not available, LSTM model will use heuristics only")


def get_collision_probability(miss_dist_km: float, rel_velocity_km_s: float,
                              fuel_fraction: float, approach_angle_deg: float) -> float:
    """Get collision probability prediction from XGBoost."""
    if collision_prob_model is None:
        initialize_ml_models()
    return collision_prob_model.predict_probability(
        miss_dist_km, rel_velocity_km_s, fuel_fraction, approach_angle_deg
    )


def get_trajectory_correction(state_history: np.ndarray) -> np.ndarray:
    """Get trajectory correction delta-v from LSTM."""
    if trajectory_model is None:
        initialize_ml_models()
    return trajectory_model.predict_correction(state_history)
