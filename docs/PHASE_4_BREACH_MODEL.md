# Phase 4 Dam Breach Hydrograph Model & Mathematical Formulation

**Reference Site**: Idukki Dam (Periyar River, Kerala)  
**Scenario**: Hypothetical Overtopping Dam-Break Baseline (`baseline_breach`)  
**Implementation**: `backend/app/hydrology/`

---

## 1. Mathematical Equations

The breach outflow hydrograph is computed by coupling empirical breach geometry evolution with transient broad-crested weir and orifice hydraulics, governed by conservation of mass in the upstream reservoir pool.

### 1.1 Breach Geometry & Formation Time (Froehlich 2008)
David C. Froehlich (2008) derived multi-variable non-linear regression equations from 74 historical dam failures:

$$\overline{B} = 0.27 \cdot K_0 \cdot V_w^{0.32} \cdot h_b^{0.04}$$

$$t_f = 63.2 \cdot \sqrt{\frac{V_w}{g \cdot h_b^2}}$$

$$Q_p = 0.607 \cdot V_w^{0.295} \cdot h_w^{1.24}$$

Where:
- $\overline{B}$ = Average breach width (meters)
- $K_0$ = Failure mode factor ($1.3$ for overtopping failure, $1.0$ for piping)
- $V_w$ = Reservoir volume involved in breach release ($m^3$)
- $h_b$ = Height of breach (meters)
- $h_w$ = Hydraulic head above breach invert at initial failure (meters)
- $t_f$ = Breach formation / development time (seconds)
- $g$ = Acceleration due to gravity ($9.81 \ \text{m/s}^2$)
- $Q_p$ = Peak discharge envelope ($m^3/s$)

The bottom width $W_b$ for a trapezoidal breach with side slope $z$ ($H:1V$) is given by:

$$W_b = \overline{B} - z \cdot h_b$$

### 1.2 Transient Breach Progression
During the formation time $0 \le t \le t_f$, breach dimensions expand from initial trigger to ultimate failure dimensions using a smooth sinusoidal S-curve:

$$\eta(t) = \frac{1}{2} \left[ 1 - \cos\left( \frac{\pi t}{t_f} \right) \right], \quad 0 \le t \le t_f$$

$$W_b(t) = W_b \cdot \eta(t)$$

$$z_{inv}(t) = z_{top} - h_b \cdot \eta(t)$$

For $t > t_f$, $\eta(t) = 1.0$ (breach geometry reaches maximum stabilized dimension).

### 1.3 Discharge Hydraulics (Broad-Crested Weir)
Discharge through the developing trapezoidal breach is computed at each time step $\Delta t$:

$$Q_{out}(t) = C_w \cdot W_b(t) \cdot H_{eff}(t)^{1.5} + C_s \cdot z \cdot H_{eff}(t)^{2.5}$$

Where:
- $C_w$ = Rectangular weir discharge coefficient = $1.70 \ \text{m}^{1/2}/\text{s}$ (SI units)
- $C_s$ = Side slope triangular weir coefficient = $1.20 \ \text{m}^{1/2}/\text{s}$
- $H_{eff}(t) = \max(0, H_{res}(t) - z_{inv}(t))$ = Effective hydraulic head above breach invert (m)

### 1.4 Reservoir Mass Conservation & Stage Drawdown
At each numerical time step $\Delta t$:

$$\Delta V = Q_{out}(t) \cdot \Delta t$$

$$V_{res}(t + \Delta t) = \max\left( 0, \ V_{res}(t) - \Delta V \right)$$

$$\Delta H = \frac{\Delta V}{A_{res}(H)}$$

$$H_{res}(t + \Delta t) = \max\left( z_{inv}(t), \ H_{res}(t) - \Delta H \right)$$

Where $A_{res}(H)$ is the reservoir surface area ($60.0 \times 10^6 \ \text{m}^2$).

---

## 2. Mass Conservation Check

Conservation of mass requires that the total integrated outflow volume equals the total volumetric drawdown from the reservoir:

$$V_{released} = \int_0^{T_{sim}} Q_{out}(t) \, dt \approx \sum_{k=1}^N \frac{Q_k + Q_{k-1}}{2} \cdot \Delta t$$

$$\epsilon_V = \frac{\left| V_{released} - \Delta V_{reservoir} \right|}{\Delta V_{reservoir}} \times 100\%$$

A scenario run is rejected if $\epsilon_V > 1.0\%$ (numerical tolerance).

---

## 3. Assumptions & Limitations

1. **Hypothetical Scenario**: The simulation models a postulated catastrophic failure under extreme PMF overtopping. Idukki is a robust double-curvature concrete arch dam with no historical breaches.
2. **Simplified Reservoir Geometry**: Surface area $A_{res}$ is treated as quasi-constant ($60 \ \text{km}^2$) over the top 35m drawdown slice, which is a standard practical assumption in macro dam-break studies.
3. **Tailwater Submergence**: Free-outflow broad-crested weir conditions are assumed at the breach crest because the steep Periyar canyon downstream ($>100\text{m}$ drop in the first kilometer) prevents significant tailwater drowning of the breach crest.
