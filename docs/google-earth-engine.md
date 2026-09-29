# Google Earth Engine & Satellite Flood Detection

## 1. Remote Sensing Flood Detection Pipeline

When Google Earth Engine (GEE) credentials are provided in `.env`, the framework connects to Google Earth Engine to retrieve pre-flood and post-flood satellite observations.

### 1.1 Sentinel-1 Synthetic Aperture Radar (SAR)
SAR is impervious to cloud cover and nocturnal illumination constraints.
- **Collection**: `COPERNICUS/S1_GRD`
- **Instrument Mode**: Interferometric Wide (IW) swath
- **Polarization**: Dual polarization ($VV$ and $VH$)
- **Algorithm**:
  1. Multi-temporal backscatter calibration: $\sigma_0\text{ (dB)} = 10 \log_{10}(\text{DN})$.
  2. Speckle noise mitigation via Refined Lee spatial filter ($7\times7$ window).
  3. Bitemporal difference: $\Delta \sigma_0 = \sigma_{0,\text{post}} - \sigma_{0,\text{pre}}$.
  4. Specular water mask thresholding: $\Delta \sigma_0 \le -3.2\text{ dB}$.

### 1.2 Sentinel-2 Multispectral (NDWI)
When optical cloud cover is $< 20\%$:
$$\text{NDWI} = \frac{\rho_{\text{Green}} - \rho_{\text{NIR}}}{\rho_{\text{Green}} + \rho_{\text{NIR}}}$$
Positive values ($\text{NDWI} > 0.0$) classify open surface water bodies.

---

## 2. Quantitative Model Validation Metrics

The framework evaluates the overlap between Model Prediction ($A_{\text{model}}$) and Satellite Observation ($A_{\text{sat}}$):

1. **Intersection over Union (IoU / Jaccard Index)**:
   $$\text{IoU} = \frac{|A_{\text{model}} \cap A_{\text{sat}}|}{|A_{\text{model}} \cup A_{\text{sat}}|}$$
2. **Precision**:
   $$\text{Precision} = \frac{|A_{\text{model}} \cap A_{\text{sat}}|}{|A_{\text{model}}|}$$
3. **Recall (Sensitivity)**:
   $$\text{Recall} = \frac{|A_{\text{model}} \cap A_{\text{sat}}|}{|A_{\text{sat}}|}$$
4. **F1-Score**:
   $$F_1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$

> **Important**: The documentation and UI clearly state that satellite observations and model simulations are distinct data products with differing temporal and spatial resolutions.
