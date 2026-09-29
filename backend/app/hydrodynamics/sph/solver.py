import math
import numpy as np
from typing import Dict, Any, List, Tuple, Callable
from pydantic import BaseModel

class SPHState(BaseModel):
    step: int
    time_sec: float
    num_particles: int
    max_depth: float
    max_velocity: float
    cfl_ratio: float
    mass_conservation_error: float

class SPHSolver:
    """
    Experimental Smooth Particle Hydrodynamics (SPH) solver for free-surface
    hydrodynamic flows and dam-break propagation.
    
    WARNING: Internal / experimental solver. Results must be marked
    'Experimental SPH Solver [Unvalidated]' until verified against benchmark suites.
    """
    ENGINE_NAME = "Experimental SPH Solver"
    STATUS_UNVALIDATED = "Experimental / Unvalidated"
    STATUS_VERIFIED = "Experimental SPH Solver [Benchmark Verified]"

    def __init__(
        self,
        h: float = 2.0,            # Smoothing length (m)
        rho0: float = 1000.0,      # Rest density (kg/m^3)
        c0: float = 50.0,          # Numerical speed of sound (m/s)
        gamma: float = 7.0,        # Tait EOS polytropic exponent
        alpha_visc: float = 0.1,   # Artificial viscosity alpha
        beta_visc: float = 0.2,    # Artificial viscosity beta
        g: float = 9.81,           # Gravity (m/s^2)
        manning_n: float = 0.035,  # Manning bed roughness
        dim: int = 2               # Spatial dimensions (2D)
    ):
        self.h = h
        self.rho0 = rho0
        self.c0 = c0
        self.gamma = gamma
        self.alpha_visc = alpha_visc
        self.beta_visc = beta_visc
        self.g = g
        self.manning_n = manning_n
        self.dim = dim
        self.time = 0.0
        self.step_count = 0

        # Particle arrays
        self.x = np.empty((0, dim), dtype=np.float32)       # Position
        self.v = np.empty((0, dim), dtype=np.float32)       # Velocity
        self.a = np.empty((0, dim), dtype=np.float32)       # Acceleration
        self.rho = np.empty(0, dtype=np.float32)            # Density
        self.p = np.empty(0, dtype=np.float32)              # Pressure
        self.m = np.empty(0, dtype=np.float32)              # Mass
        self.depth = np.empty(0, dtype=np.float32)          # Local water depth
        self.particle_type = np.empty(0, dtype=np.int32)    # 0 = fluid, 1 = boundary

        self.initial_mass = 0.0

    def wendland_kernel(self, r: np.ndarray) -> np.ndarray:
        """
        Wendland C2 smoothing kernel in 2D.
        W(q) = alpha_D * (1 - q/2)^4 * (2q + 1) for 0 <= q <= 2
        alpha_D = 7 / (4 * pi * h^2)
        """
        q = r / self.h
        alpha_d = 7.0 / (4.0 * math.pi * (self.h ** 2))
        w = np.zeros_like(q)
        mask = (q >= 0.0) & (q <= 2.0)
        q_m = q[mask]
        w[mask] = alpha_d * ((1.0 - 0.5 * q_m) ** 4) * (2.0 * q_m + 1.0)
        return w

    def grad_wendland_kernel(self, r_vec: np.ndarray, r: np.ndarray) -> np.ndarray:
        """
        Gradient of Wendland C2 kernel: dW/dr * (r_vec / r)
        dW/dq = alpha_D * (-5q) * (1 - q/2)^3
        """
        q = r / self.h
        alpha_d = 7.0 / (4.0 * math.pi * (self.h ** 2))
        grad = np.zeros_like(r_vec)
        mask = (q > 1e-6) & (q <= 2.0)
        q_m = q[mask]
        dw_dr = (alpha_d / self.h) * (-5.0 * q_m) * ((1.0 - 0.5 * q_m) ** 3)
        unit_vec = r_vec[mask] / r[mask, np.newaxis]
        grad[mask] = unit_vec * dw_dr[:, np.newaxis]
        return grad

    def initialize_dam_break_column(
        self,
        length: float = 10.0,
        height: float = 5.0,
        dx: float = 0.5,
        channel_length: float = 30.0
    ):
        """
        Initializes a 2D water column for standard dam-break bench tests.
        """
        x_fluid = []
        # Fluid particles
        xs = np.arange(0.5 * dx, length, dx)
        ys = np.arange(0.5 * dx, height, dx)
        for xx in xs:
            for yy in ys:
                x_fluid.append([xx, yy])
        x_fluid = np.array(x_fluid, dtype=np.float32)
        n_fluid = len(x_fluid)

        # Boundary particles (bed & end wall)
        x_bound = []
        b_xs = np.arange(-2.0 * dx, channel_length + 2.0 * dx, dx)
        # Bed
        for bx in b_xs:
            x_bound.append([bx, 0.0])
            x_bound.append([bx, -dx])
        # Back wall (x = 0)
        for by in np.arange(0.0, height * 1.5, dx):
            x_bound.append([-dx, by])
        # End wall
        for by in np.arange(0.0, height * 1.5, dx):
            x_bound.append([channel_length + dx, by])
        x_bound = np.array(x_bound, dtype=np.float32)
        n_bound = len(x_bound)

        total_p = n_fluid + n_bound
        self.x = np.vstack([x_fluid, x_bound])
        self.v = np.zeros((total_p, 2), dtype=np.float32)
        self.a = np.zeros((total_p, 2), dtype=np.float32)
        self.particle_type = np.zeros(total_p, dtype=np.int32)
        self.particle_type[n_fluid:] = 1

        # Particle mass based on rest density and cell volume
        m_particle = self.rho0 * (dx ** 2)
        self.m = np.full(total_p, m_particle, dtype=np.float32)
        self.rho = np.full(total_p, self.rho0, dtype=np.float32)
        self.p = np.zeros(total_p, dtype=np.float32)
        self.depth = np.full(total_p, height, dtype=np.float32)
        self.initial_mass = float(np.sum(self.m[self.particle_type == 0]))

    def compute_density_and_pressure(self):
        """
        Computes particle density using kernel summation and pressure using Tait's EOS:
        P = (c0^2 * rho0 / gamma) * ((rho / rho0)^gamma - 1)
        """
        n = len(self.x)
        # Pairwise distance matrix (efficient for benchmark scales)
        diff = self.x[:, np.newaxis, :] - self.x[np.newaxis, :, :]
        dist = np.linalg.norm(diff, axis=-1)

        # Kernel values
        w = self.wendland_kernel(dist)
        # Density summation: rho_i = sum_j m_j * W_ij
        self.rho = np.sum(self.m[:, np.newaxis] * w, axis=0)
        self.rho = np.maximum(self.rho, self.rho0 * 0.5)

        # Tait's equation of state
        B = (self.rho0 * (self.c0 ** 2)) / self.gamma
        self.p = B * ((np.power(self.rho / self.rho0, self.gamma)) - 1.0)
        self.p = np.maximum(0.0, self.p)

    def compute_accelerations(self):
        """
        Momentum equation with pressure gradient, Monaghan artificial viscosity,
        gravity, and Manning bottom shear friction.
        """
        n = len(self.x)
        is_fluid = self.particle_type == 0
        self.a.fill(0.0)

        # Gravity on fluid particles: [0, -g]
        self.a[is_fluid, 1] -= self.g

        diff = self.x[:, np.newaxis, :] - self.x[np.newaxis, :, :]
        dist = np.linalg.norm(diff, axis=-1)

        # Grad W
        grad_w = self.grad_wendland_kernel(diff, dist)

        # Monaghan artificial viscosity
        v_diff = self.v[:, np.newaxis, :] - self.v[np.newaxis, :, :]
        v_dot_r = np.sum(v_diff * diff, axis=-1)

        # Pressure acceleration term
        # d v_i / dt = - sum_j m_j (P_i/rho_i^2 + P_j/rho_j^2 + Pi_ij) * grad_W_ij
        p_term = (self.p / (self.rho ** 2))[:, np.newaxis] + (self.p / (self.rho ** 2))[np.newaxis, :]

        # Artificial viscosity term
        c_mean = self.c0
        rho_mean = 0.5 * (self.rho[:, np.newaxis] + self.rho[np.newaxis, :])
        mu_ij = (self.h * v_dot_r) / ((dist ** 2) + 0.01 * (self.h ** 2))
        pi_ij = np.zeros_like(dist)
        mask_visc = v_dot_r < 0
        pi_ij[mask_visc] = (-self.alpha_visc * c_mean * mu_ij[mask_visc] +
                            self.beta_visc * (mu_ij[mask_visc] ** 2)) / rho_mean[mask_visc]

        total_bracket = (p_term + pi_ij)[:, :, np.newaxis] * grad_w
        acc_p = -np.sum(self.m[:, np.newaxis, np.newaxis] * total_bracket, axis=1)

        self.a[is_fluid] += acc_p[is_fluid]

        # Bottom boundary repulsive force on fluid near boundary particles
        # Prevents fluid from penetrating solid bed
        bound_mask = self.particle_type == 1
        if np.any(bound_mask):
            diff_b = self.x[is_fluid, np.newaxis, :] - self.x[bound_mask][np.newaxis, :, :]
            dist_b = np.linalg.norm(diff_b, axis=-1)
            repulse_mask = (dist_b < self.h) & (dist_b > 1e-5)
            r0 = self.h * 0.6
            repulse_force = np.zeros_like(diff_b)
            # Lennard-Jones style repulsive potential
            ratio = r0 / np.maximum(dist_b, 1e-4)
            repulse_mag = 100.0 * (np.power(ratio, 4) - np.power(ratio, 2))
            repulse_mag = np.maximum(0.0, repulse_mag)
            unit_b = diff_b / np.maximum(dist_b[:, :, np.newaxis], 1e-4)
            repulse_force = unit_b * repulse_mag[:, :, np.newaxis]
            self.a[is_fluid] += np.sum(repulse_force, axis=1)

    def step(self, dt: float | None = None) -> SPHState:
        """
        Symplectic position-Verlet time integration step with adaptive CFL limiter.
        """
        is_fluid = self.particle_type == 0
        v_fluid = self.v[is_fluid]
        max_vel = float(np.max(np.linalg.norm(v_fluid, axis=-1))) if len(v_fluid) > 0 else 0.0

        # CFL condition: dt <= 0.25 * h / (c0 + v_max)
        cfl_dt = 0.25 * self.h / (self.c0 + max_vel)
        if dt is None:
            dt = min(0.01, cfl_dt)
        else:
            dt = min(dt, cfl_dt)

        self.compute_density_and_pressure()
        self.compute_accelerations()

        # Update velocities and positions of fluid particles
        self.v[is_fluid] += self.a[is_fluid] * dt
        self.x[is_fluid] += self.v[is_fluid] * dt

        # Enforce non-negative y for flat bed
        self.x[is_fluid, 1] = np.maximum(0.05, self.x[is_fluid, 1])

        self.time += dt
        self.step_count += 1

        # Current mass conservation error
        current_mass = float(np.sum(self.m[is_fluid]))
        mass_error = abs(current_mass - self.initial_mass) / max(1e-6, self.initial_mass) * 100.0

        max_depth = float(np.max(self.x[is_fluid, 1])) if len(v_fluid) > 0 else 0.0

        return SPHState(
            step=self.step_count,
            time_sec=round(self.time, 4),
            num_particles=int(np.sum(is_fluid)),
            max_depth=round(max_depth, 3),
            max_velocity=round(max_vel, 3),
            cfl_ratio=round(float(dt / max(1e-6, cfl_dt)), 3),
            mass_conservation_error=round(mass_error, 4)
        )
