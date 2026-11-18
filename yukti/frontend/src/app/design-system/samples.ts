import { ChartSpec, KpiTile, TableSpec } from '@/contracts/answerContract';

/* ------------------------------------------------------------------ KPI Samples */

export const KPI_SAMPLES: KpiTile[] = [
  {
    label: 'FY26 Standalone Revenue',
    value: 867647,
    unit: '₹ Cr',
  },
  {
    label: 'FY26 Standalone PAT',
    value: 36803,
    unit: '₹ Cr',
    delta: '+184% vs FY25',
  },
  {
    label: 'FY26 Gross Refining Margin',
    value: 8.45,
    unit: '$/bbl',
    delta: '+3.65 $/bbl vs FY25',
  },
];

/* ------------------------------------------------------------------ Table Sample */

export const TABLE_SAMPLE: TableSpec = {
  columns: ['refinery', 'state', 'capacity_mmtpa', 'throughput_mmt', 'utilization_pct', 'grm_usd_bbl'],
  rows: [
    { refinery: 'Paradip', state: 'Odisha', capacity_mmtpa: 15.0, throughput_mmt: 15.82, utilization_pct: 105.5, grm_usd_bbl: 9.2 },
    { refinery: 'Panipat', state: 'Haryana', capacity_mmtpa: 15.0, throughput_mmt: 15.41, utilization_pct: 102.7, grm_usd_bbl: 8.8 },
    { refinery: 'Koyali', state: 'Gujarat', capacity_mmtpa: 13.7, throughput_mmt: 15.18, utilization_pct: 110.8, grm_usd_bbl: 8.9 },
    { refinery: 'Mathura', state: 'Uttar Pradesh', capacity_mmtpa: 8.0, throughput_mmt: 9.15, utilization_pct: 114.4, grm_usd_bbl: 8.4 },
    { refinery: 'Haldia', state: 'West Bengal', capacity_mmtpa: 8.0, throughput_mmt: 8.42, utilization_pct: 105.3, grm_usd_bbl: 7.9 },
    { refinery: 'Barauni', state: 'Bihar', capacity_mmtpa: 6.0, throughput_mmt: 6.51, utilization_pct: 108.5, grm_usd_bbl: 7.6 },
    { refinery: 'Bongaigaon', state: 'Assam', capacity_mmtpa: 2.7, throughput_mmt: 2.84, utilization_pct: 105.2, grm_usd_bbl: 8.1 },
    { refinery: 'Guwahati & Digboi', state: 'Assam', capacity_mmtpa: 1.85, throughput_mmt: 2.12, utilization_pct: 114.6, grm_usd_bbl: 7.8 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 1: Bar */
// Throughput by refinery (8 rows)

export const BAR_SPEC: ChartSpec = {
  kind: 'bar',
  category: 'refinery',
  value: 'throughput_mmt',
  unit: 'MMT',
  data: [
    { refinery: 'Paradip', throughput_mmt: 15.82 },
    { refinery: 'Panipat', throughput_mmt: 15.41 },
    { refinery: 'Koyali', throughput_mmt: 15.18 },
    { refinery: 'Mathura', throughput_mmt: 9.15 },
    { refinery: 'Haldia', throughput_mmt: 8.42 },
    { refinery: 'Barauni', throughput_mmt: 6.51 },
    { refinery: 'Bongaigaon', throughput_mmt: 2.84 },
    { refinery: 'Guwahati', throughput_mmt: 1.38 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 2: H-Bar */
// Segment & business line EBIT contribution (illustrative sample, unit ₹ Cr)

export const HBAR_SPEC: ChartSpec = {
  kind: 'hbar',
  category: 'division',
  value: 'ebit_cr',
  unit: '₹ Cr',
  data: [
    { division: 'Petroleum Products', ebit_cr: 48620 },
    { division: 'Pipelines Network', ebit_cr: 7450 },
    { division: 'Natural Gas Marketing', ebit_cr: 1890 },
    { division: 'Explosives & Cryogenics', ebit_cr: 640 },
    { division: 'Overseas Exploration', ebit_cr: 410 },
    { division: 'Alternative Energy', ebit_cr: 215 },
    { division: 'Petrochemicals (Cycle Low)', ebit_cr: -620 },
    { division: 'Green Hydrogen Pilot', ebit_cr: -185 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 3: Donut */
// Downstream sales volume mix by product category (MMT)

export const DONUT_SPEC: ChartSpec = {
  kind: 'donut',
  category: 'product',
  value: 'volume_mmt',
  unit: 'MMT',
  data: [
    { product: 'HSD (Diesel)', volume_mmt: 41.2 },
    { product: 'MS (Petrol)', volume_mmt: 17.8 },
    { product: 'LPG (Indane)', volume_mmt: 15.4 },
    { product: 'ATF (Aviation)', volume_mmt: 4.9 },
    { product: 'Naphtha', volume_mmt: 4.1 },
    { product: 'Petrochemicals', volume_mmt: 3.3 },
    { product: 'FO / Bitumen / Lubes', volume_mmt: 6.8 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 4: Line */
// IOCL Standalone Revenue FY17–FY26 (₹ Cr)

export const LINE_SPEC: ChartSpec = {
  kind: 'line',
  category: 'fiscal_year',
  value: 'revenue_cr',
  unit: '₹ Cr',
  data: [
    { fiscal_year: 'FY17', revenue_cr: 445443 },
    { fiscal_year: 'FY18', revenue_cr: 506428 },
    { fiscal_year: 'FY19', revenue_cr: 605924 },
    { fiscal_year: 'FY20', revenue_cr: 566950 },
    { fiscal_year: 'FY21', revenue_cr: 514890 },
    { fiscal_year: 'FY22', revenue_cr: 728460 },
    { fiscal_year: 'FY23', revenue_cr: 934953 },
    { fiscal_year: 'FY24', revenue_cr: 866345 },
    { fiscal_year: 'FY25', revenue_cr: 845513 },
    { fiscal_year: 'FY26', revenue_cr: 867647 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 5: Histogram */
// Refinery daily utilisation observations (%)

const RAW_UTIL_PCT: number[] = [
  84, 86, 88, 90, 91, 92, 93, 94, 95, 95, 96, 96, 97, 97, 98, 98, 99, 99, 99, 100,
  100, 100, 101, 101, 101, 102, 102, 102, 103, 103, 103, 104, 104, 104, 104, 105, 105, 105, 105, 106,
  106, 106, 106, 107, 107, 107, 107, 108, 108, 108, 108, 109, 109, 109, 109, 110, 110, 110, 110, 111,
  111, 111, 111, 112, 112, 112, 112, 113, 113, 113, 114, 114, 114, 105, 106, 107, 108, 109, 110, 104,
  103, 102, 101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 102, 103, 104, 105, 106, 107, 108,
  105, 106, 107, 108, 109, 110, 104, 105, 106, 107, 108, 103, 102, 101, 100, 99, 104, 105, 106, 107,
  108, 96, 98, 100, 102, 104, 106, 108, 110, 112, 101, 103,
];

export const HISTOGRAM_SPEC: ChartSpec = {
  kind: 'histogram',
  value: 'utilisation_pct',
  unit: '%',
  data: RAW_UTIL_PCT.map((utilisation_pct) => ({ utilisation_pct })),
};

/* ------------------------------------------------------------------ Reference Chart 6: Treemap */
// Refining nameplate capacity by unit (MMTPA)

export const TREEMAP_SPEC: ChartSpec = {
  kind: 'treemap',
  category: 'refinery',
  value: 'capacity_mmtpa',
  unit: 'MMTPA',
  data: [
    { refinery: 'Paradip', capacity_mmtpa: 15.0 },
    { refinery: 'Panipat', capacity_mmtpa: 15.0 },
    { refinery: 'Koyali', capacity_mmtpa: 13.7 },
    { refinery: 'Mathura', capacity_mmtpa: 8.0 },
    { refinery: 'Haldia', capacity_mmtpa: 8.0 },
    { refinery: 'Barauni', capacity_mmtpa: 6.0 },
    { refinery: 'Bongaigaon', capacity_mmtpa: 2.7 },
    { refinery: 'Guwahati & Digboi', capacity_mmtpa: 1.85 },
  ],
};

/* ------------------------------------------------------------------ Reference Chart 7: Ranked H-Bar */
// Refinery capacity & petrochemical integration ranked index

export const RANKED_SPEC: ChartSpec = {
  kind: 'hbar',
  category: 'unit',
  value: 'throughput_mmt',
  unit: 'MMT',
  sort: 'desc',
  data: [
    { unit: 'Paradip Refinery', throughput_mmt: 15.82 },
    { unit: 'Panipat Refinery', throughput_mmt: 15.41 },
    { unit: 'Koyali Refinery', throughput_mmt: 15.18 },
    { unit: 'Mathura Refinery', throughput_mmt: 9.15 },
    { unit: 'Haldia Refinery', throughput_mmt: 8.42 },
    { unit: 'Barauni Refinery', throughput_mmt: 6.51 },
    { unit: 'Bongaigaon Refinery', throughput_mmt: 2.84 },
    { unit: 'Guwahati Refinery', throughput_mmt: 1.38 },
    { unit: 'Digboi Refinery', throughput_mmt: 0.74 },
  ],
};
