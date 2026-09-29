import math
from typing import List
from backend.app.hydrology.breach_base import BreachParameters, BreachGeometry, HydrographPoint
from backend.app.hydrology.froehlich import Froehlich2008BreachModel
from backend.app.hydrology.macdonald import MacDonald1984BreachModel
from backend.app.hydrology.von_thun import VonThun1990BreachModel

class HydrographGenerator:
    """
    Computes dynamic breach discharge Q(t) and reservoir stage-storage drawdown
    using broad-crested weir and orifice hydraulics with mass balance routing.
    """

    @classmethod
    def get_model(cls, formulation: str):
        f = formulation.lower()
        if "macdonald" in f:
            return MacDonald1984BreachModel()
        elif "vonthun" in f or "von_thun" in f:
            return VonThun1990BreachModel()
        else:
            return Froehlich2008BreachModel()

    @classmethod
    def generate_hydrograph(
        cls,
        params: BreachParameters,
        formulation: str = "Froehlich_2008",
        custom_geometry: BreachGeometry | None = None,
        total_duration_hours: float = 6.0,
        dt_seconds: float = 60.0
    ) -> List[HydrographPoint]:
        if custom_geometry:
            geom = custom_geometry
        else:
            model = cls.get_model(formulation)
            geom = model.calculate_geometry(params)

        V_current = params.reservoir_volume
        H_initial = params.reservoir_level
        H_current = H_initial
        A_res = max(1000.0, params.reservoir_area)
        tf = max(60.0, geom.breach_time_sec)
        Wb_final = geom.breach_bottom_width
        z = geom.breach_side_slope_z
        hb_final = geom.breach_depth

        points: List[HydrographPoint] = []
        total_steps = int((total_duration_hours * 3600.0) / dt_seconds)
        t = 0.0

        # Broad crested weir discharge coefficient Cw ~ 1.7 (SI)
        Cw = 1.70
        g = 9.81

        for step in range(total_steps + 1):
            # Breach expansion ratio over formation time tf (linear or sinusoidal)
            if t <= tf:
                # Sinusoidal ramp for realistic erosion curve
                progress = 0.5 * (1.0 - math.cos(math.pi * t / tf))
            else:
                progress = 1.0

            # Current breach bottom width and depth
            Wb_t = max(0.5, Wb_final * progress)
            hb_t = hb_final * progress
            # Invert elevation drop
            z_invert = hb_final * (1.0 - progress)

            # Hydraulic head above current breach invert
            head = max(0.0, H_current - z_invert)
            
            if head > 0.0:
                # Flow through trapezoidal breach section: Q = Cw * Wb * H^1.5 + Cw_side * z * H^2.5
                # Standard formula: Q = 1.70 * Wb * H^1.5 + 1.25 * z * H^2.5
                Q_weir = (Cw * Wb_t * (head ** 1.5)) + (1.20 * z * (head ** 2.5))
                Q_out = max(0.0, Q_weir)
            else:
                Q_out = 0.0

            # Tailwater velocity estimation (v = Q / A_channel)
            # Assuming downstream corridor average width ~ 80m
            A_ch = max(10.0, 80.0 * max(0.5, head * 0.4))
            v_flow = Q_out / A_ch

            points.append(HydrographPoint(
                time_sec=round(t, 1),
                time_min=round(t / 60.0, 2),
                discharge_m3s=round(Q_out, 2),
                stage_m=round(H_current, 3),
                velocity_ms=round(v_flow, 2),
                reservoir_volume_m3=round(V_current, 1)
            ))

            # Mass balance step: dV = -Q * dt
            dV = Q_out * dt_seconds
            V_current = max(0.0, V_current - dV)
            # Stage drawdown: dH = dV / A_res
            dH = dV / A_res
            H_current = max(0.0, H_current - dH)

            t += dt_seconds
            if V_current <= 0.0 and t > tf:
                break

        return points
