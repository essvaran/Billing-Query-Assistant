export function fmtUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (value === 0) {
    return '$0';
  }
  if (value < 0.01) {
    return '$' + value.toFixed(6);
  }
  return '$' + value.toFixed(4);
}

export function fmtMs(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'not logged';
  }
  return value >= 1000 ? (value / 1000).toFixed(2) + ' s' : value.toFixed(0) + ' ms';
}

export function fmtUtc(ts: string | null | undefined): string {
  if (!ts) {
    return '-';
  }
  const d = new Date(ts);
  if (isNaN(d.getTime())) {
    return ts;
  }
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

export function mmss(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return String(m).padStart(2, '0') + ':' + String(rest).padStart(2, '0');
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : '-';
}

/** 'YYYY-MM-DDTHH:mm' typed in a datetime-local box, interpreted as UTC. */
export function utcInputToIso(value: string): string | undefined {
  return value ? value + ':00Z' : undefined;
}

export function utcInputFor(date: Date): string {
  return date.toISOString().slice(0, 16);
}

export function yesterdayWindowUtc(): { after: string; before: string } {
  const start = new Date();
  start.setUTCDate(start.getUTCDate() - 1);
  start.setUTCHours(12, 0, 0, 0);
  const end = new Date(start.getTime());
  end.setUTCHours(18, 0, 0, 0);
  return { after: utcInputFor(start), before: utcInputFor(end) };
}
