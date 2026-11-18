/**
 * Geographic coordinates (lat/lon) for IndianOil's 9 standalone refineries, major hubs, and HQs.
 * Used by MapRenderer and offline/demo map contracts.
 */
export interface IoclLocationCoord {
  code: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  kind: 'Refinery' | 'HQ' | 'Hub';
}

export const IOCL_LOCATIONS: IoclLocationCoord[] = [
  { code: 'REF-PNP', name: 'Panipat Refinery & Petrochemical Complex', city: 'Panipat', lat: 29.4765, lon: 76.8906, kind: 'Refinery' },
  { code: 'REF-PRD', name: 'Paradip Refinery', city: 'Paradip', lat: 20.2644, lon: 86.6114, kind: 'Refinery' },
  { code: 'REF-KYL', name: 'Koyali (Gujarat) Refinery', city: 'Vadodara', lat: 22.3692, lon: 73.1128, kind: 'Refinery' },
  { code: 'REF-MTR', name: 'Mathura Refinery', city: 'Mathura', lat: 27.3924, lon: 77.6844, kind: 'Refinery' },
  { code: 'REF-HLD', name: 'Haldia Refinery', city: 'Haldia', lat: 22.0497, lon: 88.1069, kind: 'Refinery' },
  { code: 'REF-BRN', name: 'Barauni Refinery', city: 'Barauni', lat: 25.4397, lon: 86.0869, kind: 'Refinery' },
  { code: 'REF-BNG', name: 'Bongaigaon Refinery', city: 'Bongaigaon', lat: 26.4716, lon: 90.5177, kind: 'Refinery' },
  { code: 'REF-GHY', name: 'Guwahati Refinery', city: 'Guwahati', lat: 26.1886, lon: 91.7975, kind: 'Refinery' },
  { code: 'REF-DGB', name: 'Digboi Refinery', city: 'Digboi', lat: 27.3886, lon: 95.6292, kind: 'Refinery' },
  { code: 'WC-DEL', name: 'IndianOil Bhavan (New Delhi HQ)', city: 'Delhi', lat: 28.5906, lon: 77.2432, kind: 'HQ' },
  { code: 'WC-MUM', name: 'IndianOil Bhavan (Mumbai HQ)', city: 'Mumbai', lat: 19.0644, lon: 72.8669, kind: 'HQ' },
  { code: 'WC-NOI', name: 'IndianOil Pipeline & Marketing Hub (Noida)', city: 'Noida', lat: 28.5355, lon: 77.3910, kind: 'Hub' },
  { code: 'WC-FBD', name: 'IndianOil R&D Centre (Faridabad)', city: 'Faridabad', lat: 28.4089, lon: 77.3178, kind: 'Hub' },
  { code: 'CPCL', name: 'Chennai Petroleum Corporation Ltd (CPCL)', city: 'Chennai', lat: 13.1649, lon: 80.2683, kind: 'Refinery' },
];

export function resolveIoclCoords(nameOrCode: string): { lat: number; lon: number } | null {
  const q = String(nameOrCode || '').trim().toLowerCase();
  if (!q) return null;
  for (const loc of IOCL_LOCATIONS) {
    if (
      q === loc.code.toLowerCase() ||
      q === loc.city.toLowerCase() ||
      q.includes(loc.city.toLowerCase()) ||
      q.includes(loc.code.toLowerCase()) ||
      (loc.code === 'REF-KYL' && q.includes('koyali'))
    ) {
      return { lat: loc.lat, lon: loc.lon };
    }
  }
  return null;
}
