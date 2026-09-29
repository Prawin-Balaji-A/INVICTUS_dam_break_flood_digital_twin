import math
from backend.app.hydrology.breach_base import BreachModel, BreachParameters, BreachGeometry

class Froehlich2008BreachModel(BreachModel):
    """
    Froehlich (2008) empirical dam breach equations based on 74 historic embankment dam failures.
    Citation: Froehlich, D. C. (2008). Embankment dam breach parameters and their uncertainties.
    Journal of Hydraulic Engineering, 134(12), 1708-1721.
    """

    def calculate_geometry(self, params: BreachParameters) -> BreachGeometry:
        Vw = max(100.0, params.reservoir_volume)
        hb = min(params.dam_height, params.reservoir_level)
        
        # Mode factor K0
        # K0 = 1.4 for overtopping; K0 = 1.0 for piping/other
        is_overtopping = params.failure_mode.lower() == "overtopping"
        K0 = 1.4 if is_overtopping else 1.0
        
        # Side slope z (H:V)
        # z = 1.0 for overtopping; z = 0.7 for piping
        z = 1.0 if is_overtopping else 0.7

        # Average breach width (m)
        # Bavg = 0.27 * K0 * (Vw ** 0.32) * (hb ** 0.04) (froehlich 2008)
        Bavg = 0.27 * K0 * (Vw ** 0.32) * (hb ** 0.04)
        Bavg = min(Bavg, params.dam_length * 0.95)

        # Breach formation time (hours -> seconds)
        # tf = 63.2 * (Vw / (g * hb^2))^0.5 -> Froehlich regression: tf = 0.00254 * (Vw ** 0.53) * (hb ** -0.90) hours
        tf_hours = 0.00254 * (Vw ** 0.53) * (hb ** -0.90)
        tf_sec = max(300.0, tf_hours * 3600.0)

        # Bottom and top width from trapezoidal geometry: Bavg = Wb + z * hb
        Wb = max(5.0, Bavg - z * hb)
        Wt = Wb + 2.0 * z * hb
        Bavg = (Wb + Wt) / 2.0

        # Empirical peak discharge estimation for validation check: Qp = 0.607 * Vw^0.295 * hw^1.24
        Qp = 0.607 * (Vw ** 0.295) * (hb ** 1.24)

        return BreachGeometry(
            formulation_name="Froehlich (2008)",
            breach_width_avg=round(Bavg, 2),
            breach_bottom_width=round(Wb, 2),
            breach_top_width=round(Wt, 2),
            breach_depth=round(hb, 2),
            breach_time_sec=round(tf_sec, 1),
            breach_side_slope_z=z,
            peak_discharge_m3s=round(Qp, 2)
        )
