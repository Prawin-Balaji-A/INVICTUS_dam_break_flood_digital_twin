from backend.app.hydrology.breach_base import BreachModel, BreachParameters, BreachGeometry

class VonThun1990BreachModel(BreachModel):
    """
    Von Thun & Gillette (1990) empirical dam breach equations.
    Citation: Von Thun, J. L., & Gillette, D. R. (1990). Guidance on breach parameters.
    U.S. Bureau of Reclamation, Denver, Colorado.
    """

    def calculate_geometry(self, params: BreachParameters) -> BreachGeometry:
        Vw = max(100.0, params.reservoir_volume)
        hw = min(params.dam_height, params.reservoir_level)
        hb = hw

        # Cb factor based on reservoir volume (m^3)
        if Vw < 1.23e6:
            Cb = 6.1
        elif Vw < 6.17e6:
            Cb = 18.3
        elif Vw < 1.23e7:
            Cb = 30.5
        else:
            Cb = 45.7

        # Average breach width Bavg = 2.5 * hw + Cb
        Bavg = 2.5 * hw + Cb
        Bavg = min(Bavg, params.dam_length * 0.95)

        # Side slope z = 1.0 (for cohesive materials / typical dams) or 0.5
        z = 1.0
        Wb = max(5.0, Bavg - z * hb)
        Wt = Wb + 2.0 * z * hb
        Bavg = (Wb + Wt) / 2.0

        # Formation time tf (hours):
        # tf = Bavg / (4 * hw) or tf = 0.015 * hw (erosion resistant) / 0.020 * hw (easily erodible)
        # Using intermediate: tf = 0.017 * hw
        tf_hours = max(0.15, 0.017 * hw)
        tf_sec = max(300.0, tf_hours * 3600.0)

        # Peak discharge estimate
        Qp = 0.607 * (Vw ** 0.295) * (hw ** 1.24)

        return BreachGeometry(
            formulation_name="Von Thun & Gillette (1990)",
            breach_width_avg=round(Bavg, 2),
            breach_bottom_width=round(Wb, 2),
            breach_top_width=round(Wt, 2),
            breach_depth=round(hb, 2),
            breach_time_sec=round(tf_sec, 1),
            breach_side_slope_z=z,
            peak_discharge_m3s=round(Qp, 2)
        )
