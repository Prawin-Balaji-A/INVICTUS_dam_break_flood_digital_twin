import math
from backend.app.hydrology.breach_base import BreachModel, BreachParameters, BreachGeometry

class MacDonald1984BreachModel(BreachModel):
    """
    MacDonald & Langridge-Monopolis (1984) breach formulation.
    Citation: MacDonald, T. C., & Langridge-Monopolis, J. (1984).
    Breaching characteristics of dam failures. Journal of Hydraulic Engineering, 110(5), 567-586.
    """

    def calculate_geometry(self, params: BreachParameters) -> BreachGeometry:
        Vw = max(100.0, params.reservoir_volume)
        hw = min(params.dam_height, params.reservoir_level)
        hb = hw

        # Breach formation factor Vout * hw (m^4)
        # Ver = 0.0261 * (Vw * hw)^0.769 (eroded volume in m^3)
        Ver = 0.0261 * ((Vw * hw) ** 0.769)

        # Breach formation time tf (hours -> seconds)
        # tf = 0.0179 * (Ver ** 0.364)
        tf_hours = 0.0179 * (Ver ** 0.364)
        tf_sec = max(300.0, tf_hours * 3600.0)

        # Side slope z (standard 0.5 for rockfill/compacted earth)
        z = 0.5
        
        # Bottom width Wb = (Ver - hb^2 * z * Ld/2) / (hb * Ld) approximate
        # Typically Wb = Bavg - z * hb
        Bavg = max(10.0, (Ver / (hb * max(10.0, params.dam_length))) * 1.5)
        Bavg = min(Bavg, params.dam_length * 0.95)
        Wb = max(5.0, Bavg - z * hb)
        Wt = Wb + 2.0 * z * hb
        Bavg = (Wb + Wt) / 2.0

        # Peak discharge estimate
        Qp = 1.154 * ((Vw * hw) ** 0.412)

        return BreachGeometry(
            formulation_name="MacDonald & Langridge-Monopolis (1984)",
            breach_width_avg=round(Bavg, 2),
            breach_bottom_width=round(Wb, 2),
            breach_top_width=round(Wt, 2),
            breach_depth=round(hb, 2),
            breach_time_sec=round(tf_sec, 1),
            breach_side_slope_z=z,
            peak_discharge_m3s=round(Qp, 2)
        )
