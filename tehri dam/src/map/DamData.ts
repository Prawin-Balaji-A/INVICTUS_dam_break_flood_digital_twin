// ============================================================
// DamData.ts — Major dams of India.
// Coordinates are true lat/lng; the map projects them at render time
// (see IndiaOutline.projectGeo), so there are no baked screen coords.
// Height (m) and gross storage (MCM) are widely-cited public figures,
// representative rather than authoritative.
// ============================================================

export interface DamInfo {
  name: string;
  state: string;
  river: string;
  lat: number;
  lng: number;
  height: number;   // structural height, metres
  year: number;     // year commissioned
  capacity?: number; // gross storage, million m³ (MCM)
  type?: string;      // structural type (gravity, embankment, arch…)
  purpose?: string;   // primary purposes
  length?: number;    // crest length, metres
  installedMW?: number; // installed hydro-power capacity, MW
  renovated?: number;   // year of last major rehabilitation / strengthening
  authority?: string;   // owning / operating authority
  event?: { year: number; text: string }; // a notable documented event
}

function dam(
  name: string, state: string, river: string,
  lat: number, lng: number, height: number, year: number,
  capacity?: number, extra?: Partial<DamInfo>
): DamInfo {
  return { name, state, river, lat, lng, height, year, capacity, ...extra };
}

// Technical + historical details below (type, purpose, operator, notable
// events) are indicative, compiled from widely-cited public sources — like the
// height/storage figures, representative rather than authoritative.
export const INDIAN_DAMS: DamInfo[] = [
  dam("Tehri Dam", "Uttarakhand", "Bhagirathi", 30.38, 78.48, 260, 2006, 3540,
    { type: "Earth & rockfill embankment", purpose: "Hydropower, irrigation & water supply", length: 575, installedMW: 1000, authority: "THDC India Ltd." }),
  dam("Bhakra Dam", "Himachal Pradesh", "Sutlej", 31.42, 76.43, 226, 1963, 9340,
    { type: "Concrete gravity", purpose: "Irrigation & hydropower", length: 518, installedMW: 1325, authority: "Bhakra Beas Management Board" }),
  dam("Sardar Sarovar Dam", "Gujarat", "Narmada", 21.83, 73.75, 163, 2017, 9500,
    { type: "Concrete gravity", purpose: "Irrigation, hydropower & water supply", length: 1210, installedMW: 1450, authority: "Sardar Sarovar Narmada Nigam Ltd." }),
  dam("Hirakud Dam", "Odisha", "Mahanadi", 21.52, 83.87, 61, 1957, 8136,
    { type: "Composite earthen & masonry", purpose: "Flood control, irrigation & hydropower", installedMW: 348, authority: "Govt. of Odisha" }),
  dam("Nagarjuna Sagar Dam", "Telangana", "Krishna", 16.57, 79.31, 124, 1967, 11472,
    { type: "Masonry gravity", purpose: "Irrigation & hydropower", installedMW: 816, authority: "Govt. of Telangana / A.P." }),
  dam("Srisailam Dam", "Andhra Pradesh", "Krishna", 15.85, 78.87, 143, 1981, 8722,
    { type: "Masonry & concrete gravity", purpose: "Hydropower & irrigation", installedMW: 1670, authority: "Govt. of A.P. / Telangana" }),
  dam("Koyna Dam", "Maharashtra", "Koyna", 17.40, 73.75, 103, 1964, 2797,
    { type: "Rubble-concrete gravity", purpose: "Hydropower", installedMW: 1960, renovated: 2006, authority: "Govt. of Maharashtra",
      event: { year: 1967, text: "The M6.3 Koynanagar earthquake — a noted case of reservoir-triggered seismicity — damaged the dam. It was strengthened afterwards, and again in the 2000s." } }),
  dam("Idukki Dam", "Kerala", "Periyar", 9.84, 76.97, 169, 1976, 1996,
    { type: "Double-curvature arch", purpose: "Hydropower", installedMW: 780, authority: "Kerala State Electricity Board",
      event: { year: 2018, text: "Shutters were opened for the first time in 26 years during the Kerala floods." } }),
  dam("Mettur Dam", "Tamil Nadu", "Cauvery", 11.80, 77.80, 65, 1934, 2648,
    { type: "Concrete gravity", purpose: "Irrigation & hydropower", installedMW: 200, authority: "Govt. of Tamil Nadu" }),
  dam("Tungabhadra Dam", "Karnataka", "Tungabhadra", 15.27, 76.33, 50, 1953, 3765,
    { type: "Masonry & earthen", purpose: "Irrigation & hydropower", authority: "Tungabhadra Board" }),
  dam("Bhavanisagar Dam", "Tamil Nadu", "Bhavani", 11.47, 77.08, 32, 1955, 910,
    { type: "Earthen embankment", purpose: "Irrigation", authority: "Govt. of Tamil Nadu" }),
  dam("Krishna Raja Sagara Dam", "Karnataka", "Cauvery", 12.42, 76.57, 40, 1932, 1369,
    { type: "Masonry gravity", purpose: "Irrigation & water supply", authority: "Govt. of Karnataka" }),
  dam("Mullaperiyar Dam", "Kerala", "Periyar", 9.53, 77.15, 54, 1895, 443,
    { type: "Lime-surkhi masonry gravity", purpose: "Irrigation & hydropower", renovated: 1980, authority: "Operated by Tamil Nadu, in Kerala",
      event: { year: 1979, text: "Safety concerns prompted major strengthening works; the structure remains the subject of a long-running interstate review." } }),
  dam("Ukai Dam", "Gujarat", "Tapi", 21.25, 73.58, 69, 1972, 8510,
    { type: "Earthen & masonry", purpose: "Irrigation, hydropower & flood control", installedMW: 305, authority: "Govt. of Gujarat" }),
  dam("Rihand Dam", "Uttar Pradesh", "Rihand", 24.20, 83.00, 91, 1962, 10600,
    { type: "Concrete gravity", purpose: "Hydropower & irrigation", installedMW: 300, authority: "Govt. of Uttar Pradesh" }),
  dam("Maithon Dam", "Jharkhand", "Barakar", 23.78, 86.82, 56, 1957, 1348,
    { type: "Composite concrete & earthen", purpose: "Flood control & hydropower", authority: "Damodar Valley Corporation" }),
  dam("Panchet Dam", "Jharkhand", "Damodar", 23.67, 86.73, 49, 1959, 1497,
    { type: "Earthen & concrete", purpose: "Flood control & hydropower", authority: "Damodar Valley Corporation" }),
  dam("Farakka Barrage", "West Bengal", "Ganges", 24.81, 87.92, 15, 1975, 55,
    { type: "Barrage", purpose: "River diversion & navigation", length: 2245, authority: "Farakka Barrage Project" }),
  dam("Cheruthoni Dam", "Kerala", "Cheruthoni", 9.84, 76.98, 138, 1976, 1996,
    { type: "Concrete gravity", purpose: "Hydropower (Idukki complex)", authority: "Kerala State Electricity Board",
      event: { year: 2018, text: "Its shutters were opened during the 2018 Kerala floods alongside the Idukki arch dam." } }),
  dam("Indira Sagar Dam", "Madhya Pradesh", "Narmada", 22.28, 76.47, 92, 2005, 12220,
    { type: "Concrete gravity", purpose: "Irrigation & hydropower", installedMW: 1000, authority: "Narmada Hydroelectric Dev. Corp." }),
  dam("Almatti Dam", "Karnataka", "Krishna", 16.33, 75.88, 52, 2005, 3105,
    { type: "Gravity & earthen", purpose: "Irrigation & hydropower", installedMW: 290, authority: "Govt. of Karnataka" }),
  dam("Jayakwadi Dam", "Maharashtra", "Godavari", 19.51, 75.38, 37, 1976, 2909,
    { type: "Earthen embankment", purpose: "Irrigation & water supply", authority: "Govt. of Maharashtra" }),
  dam("Bisalpur Dam", "Rajasthan", "Banas", 25.92, 75.55, 39, 1999, 1096,
    { type: "Concrete gravity", purpose: "Water supply & irrigation", authority: "Govt. of Rajasthan" }),
  dam("Tawa Dam", "Madhya Pradesh", "Tawa", 22.63, 77.82, 58, 1978, 2312,
    { type: "Masonry & earthen", purpose: "Irrigation", authority: "Govt. of Madhya Pradesh" }),
  dam("Nathpa Jhakri Dam", "Himachal Pradesh", "Sutlej", 31.55, 77.70, 60, 2004, 27,
    { type: "Concrete gravity (run-of-river)", purpose: "Hydropower", installedMW: 1500, authority: "SJVN Ltd." }),
];
