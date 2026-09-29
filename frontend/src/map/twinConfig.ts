// Single source of truth for the authoritative-terrain grid resolution shared by
// the 2D MapLibre map and the 3D Digital Twin. Both views fetch
// GET /api/simulation/{ref}/terrain?res=TWIN_GRID_RES, so their flood footprints
// are cell-identical at the same currentTimeMin (2D/3D parity). Changing this one
// value re-aligns both surfaces together — never set per-view resolutions again.
export const TWIN_GRID_RES = 260;
