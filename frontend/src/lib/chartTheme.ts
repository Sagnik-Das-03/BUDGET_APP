export interface ChartTheme {
  text: string;
  muted: string;
  grid: string;
  tooltipBg: string;
  tooltipBorder: string;
}

const LIGHT: ChartTheme = {
  text: '#0b0b0b',
  muted: '#6b6a64',
  grid: '#e1e0d9',
  tooltipBg: '#fcfcfb',
  tooltipBorder: '#e1e0d9',
};

const DARK: ChartTheme = {
  text: '#f2f1ee',
  muted: '#a3a199',
  grid: 'rgba(255,255,255,0.1)',
  tooltipBg: '#1c1b19',
  tooltipBorder: 'rgba(255,255,255,0.1)',
};

export function chartTheme(isDark: boolean): ChartTheme {
  return isDark ? DARK : LIGHT;
}
