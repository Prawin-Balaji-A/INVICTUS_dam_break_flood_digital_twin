# Hydrodynamic Modelling & Dam Breach Formulations

## 1. Mathematical Hydraulics of Dam Failure

The breach outflow hydrograph $Q(t)$ is modeled as an unsteady open-channel routing problem combining broad-crested weir mechanics and reservoir water balance.

### 1.1 Empirical Breach Geometry Formulations

#### 1. Froehlich (2008)
Based on 74 historical dam failures:
$$B_{avg} = 0.27 K_0 V_w^{0.32} h_b^{0.04}$$
$$t_f = 0.00254 V_w^{0.53} h_b^{-0.90} \quad (\text{hours})$$
Where:
- $B_{avg}$ is average breach width (m)
- $K_0 = 1.4$ for overtopping, $1.0$ for piping
- $V_w$ is reservoir volume at failure ($m^3$)
- $h_b$ is breach height (m)
- Side slope $z = 1.0\text{H}:1.0\text{V}$ (overtopping) or $0.7\text{H}:1.0\text{V}$ (piping)

#### 2. MacDonald & Langridge-Monopolis (1984)
$$V_{er} = 0.0261 (V_w h_w)^{0.769}$$
$$t_f = 0.0179 V_{er}^{0.364} \quad (\text{hours})$$
Where $V_{er}$ is the volume of eroded embankment material ($m^3$).

#### 3. Von Thun & Gillette (1990)
$$B_{avg} = 2.5 h_w + C_b$$
$$t_f = 0.017 h_w \quad (\text{hours})$$
Where $C_b$ is a coefficient function of reservoir volume ($6.1$ to $45.7\text{ m}$).

---

## 2. Dynamic Outflow Routing

Discharge through the expanding breach is calculated at each time interval $\Delta t$:
$$Q(t) = C_w W_b(t) (H(t) - z_b(t))^{1.5} + C_d z (H(t) - z_b(t))^{2.5}$$
With reservoir mass conservation drawdown:
$$\frac{dV(t)}{dt} = -Q(t), \quad \Delta H(t) = \frac{Q(t) \Delta t}{A_s(t)}$$
Where $C_w \approx 1.70$ is the broad-crested weir coefficient (SI metric units).
