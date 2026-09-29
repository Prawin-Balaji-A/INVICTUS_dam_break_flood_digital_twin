# Smooth Particle Hydrodynamics (SPH) Engine

## 1. Scientific Principles of SPH

Smooth Particle Hydrodynamics is a mesh-free, Lagrangian numerical method representing continuous fluid volume by a collection of discrete interacting particles.

### 1.1 Smoothing Kernel (Wendland $C^2$)
In 2D, the Wendland $C^2$ kernel ensures positive definiteness and eliminates tensile particle instabilities:
$$W(r, h) = \frac{7}{4\pi h^2} \left(1 - \frac{q}{2}\right)^4 (2q + 1) \quad \text{for } 0 \le q \le 2$$
Where $q = r/h$, and $h$ is the smoothing length.

### 1.2 Density & Equation of State
Particle density is calculated by kernel summation:
$$\rho_i = \sum_j m_j W(r_{ij}, h)$$
Hydrostatic and dynamic fluid pressure is computed using the weakly compressible Tait equation of state:
$$P_i = \frac{c_0^2 \rho_0}{\gamma} \left[ \left(\frac{\rho_i}{\rho_0}\right)^\gamma - 1 \right]$$
Where $\gamma = 7.0$, $\rho_0 = 1000\text{ kg/m}^3$, and $c_0 \ge 10 v_{max}$ to limit density fluctuations to $< 1\%$.

### 1.3 Momentum Conservation & Bottom Friction
$$\frac{d\vec{v}_i}{dt} = - \sum_j m_j \left( \frac{P_i}{\rho_i^2} + \frac{P_j}{\rho_j^2} + \Pi_{ij} \right) \nabla_i W_{ij} + \vec{g} - \frac{g n^2 |\vec{v}_i| \vec{v}_i}{h_i^{4/3}}$$
Where $\Pi_{ij}$ is the Monaghan artificial viscosity and $n$ is Manning's bed roughness.

---

## 2. Benchmark Validation Protocol

The internal SPH solver must maintain the label **`Experimental SPH Solver [Unvalidated]`** until passing the benchmark verification suite.

### Benchmark 1: Ritter (1892) 1D Dam-Break
- Compares simulated wavefront propagation velocity against analytical celerity $c = 2\sqrt{gh_0}$.
- Evaluates parabolic free surface profile $h(x, t) = \frac{4}{9g} (\sqrt{gh_0} - \frac{x}{2t})^2$.

### Benchmark 2: Martin & Moyce (1952) Column Collapse
- Compares non-dimensional surge front position $Z = x/a$ against non-dimensional time $T = t\sqrt{g/a}$.

### Acceptance Pass Criteria
- **Mass Conservation Error**: $\le 1.5\%$
- **Depth Goodness of Fit ($R^2$)**: $\ge 0.70$
- **Courant-Friedrichs-Lewy (CFL) Ratio**: $\le 1.00$
