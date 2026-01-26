import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface Theme {
  name: string;
  label: string;
  colors: {
    primary: string;
    primaryForeground: string;
    accent: string;
    accentForeground: string;
  };
}

export const themes: Theme[] = [
  {
    name: 'emerald-night',
    label: 'Emerald Night',
    colors: {
      primary: '158 64% 42%',
      primaryForeground: '158 50% 98%',
      accent: '38 92% 55%',
      accentForeground: '38 100% 10%',
    },
  },
  {
    name: 'sapphire',
    label: 'Sapphire',
    colors: {
      primary: '217 91% 55%',
      primaryForeground: '217 100% 98%',
      accent: '38 92% 55%',
      accentForeground: '38 100% 10%',
    },
  },
  {
    name: 'amethyst',
    label: 'Amethyst',
    colors: {
      primary: '270 60% 55%',
      primaryForeground: '270 100% 98%',
      accent: '340 75% 55%',
      accentForeground: '340 100% 98%',
    },
  },
  {
    name: 'rose-gold',
    label: 'Rose Gold',
    colors: {
      primary: '340 75% 55%',
      primaryForeground: '340 100% 98%',
      accent: '38 92% 55%',
      accentForeground: '38 100% 10%',
    },
  },
  {
    name: 'amber',
    label: 'Amber',
    colors: {
      primary: '38 80% 50%',
      primaryForeground: '38 100% 10%',
      accent: '158 64% 42%',
      accentForeground: '158 50% 98%',
    },
  },
  {
    name: 'monochrome',
    label: 'Monochrome',
    colors: {
      primary: '220 10% 50%',
      primaryForeground: '220 10% 98%',
      accent: '220 15% 60%',
      accentForeground: '220 15% 10%',
    },
  },
  {
    name: 'ocean-depths',
    label: 'Ocean Depths',
    colors: {
      primary: '195 85% 45%',
      primaryForeground: '195 100% 98%',
      accent: '175 70% 40%',
      accentForeground: '175 100% 98%',
    },
  },
  {
    name: 'sunset-blaze',
    label: 'Sunset Blaze',
    colors: {
      primary: '25 95% 55%',
      primaryForeground: '25 100% 98%',
      accent: '350 85% 55%',
      accentForeground: '350 100% 98%',
    },
  },
  {
    name: 'forest-moss',
    label: 'Forest Moss',
    colors: {
      primary: '85 45% 40%',
      primaryForeground: '85 50% 98%',
      accent: '45 70% 50%',
      accentForeground: '45 100% 10%',
    },
  },
  {
    name: 'midnight-cherry',
    label: 'Midnight Cherry',
    colors: {
      primary: '330 65% 50%',
      primaryForeground: '330 100% 98%',
      accent: '280 50% 55%',
      accentForeground: '280 100% 98%',
    },
  },
  {
    name: 'arctic-frost',
    label: 'Arctic Frost',
    colors: {
      primary: '200 60% 60%',
      primaryForeground: '200 100% 10%',
      accent: '180 40% 70%',
      accentForeground: '180 100% 10%',
    },
  },
];

interface ThemeContextType {
  currentTheme: Theme;
  setTheme: (themeName: string) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'bookkeep-theme';

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const { colors } = theme;

  // Primary colors
  root.style.setProperty('--primary', colors.primary);
  root.style.setProperty('--primary-foreground', colors.primaryForeground);

  // Accent colors
  root.style.setProperty('--accent', colors.accent);
  root.style.setProperty('--accent-foreground', colors.accentForeground);

  // Ring matches primary
  root.style.setProperty('--ring', colors.primary);

  // Sidebar colors
  root.style.setProperty('--sidebar-primary', colors.primary);
  root.style.setProperty('--sidebar-primary-foreground', colors.primaryForeground);
  root.style.setProperty('--sidebar-ring', colors.primary);

  // Success matches primary (for consistency)
  root.style.setProperty('--success', colors.primary);
  root.style.setProperty('--success-foreground', colors.primaryForeground);

  // Warning matches accent
  root.style.setProperty('--warning', colors.accent);
  root.style.setProperty('--warning-foreground', colors.accentForeground);

  // Chart colors derived from primary/accent
  root.style.setProperty('--chart-1', colors.primary);
  root.style.setProperty('--chart-2', colors.accent);

  // Update glow effect based on primary color
  const glowValue = `0 0 40px hsl(${colors.primary} / 0.3), 0 0 80px hsl(${colors.primary} / 0.15)`;
  root.style.setProperty('--glow-emerald', glowValue);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [currentTheme, setCurrentTheme] = useState<Theme>(() => {
    // Load saved theme from localStorage
    const savedThemeName = localStorage.getItem(STORAGE_KEY);
    const savedTheme = themes.find(t => t.name === savedThemeName);
    return savedTheme || themes[0]; // Default to Emerald Night
  });

  useEffect(() => {
    // Apply theme on mount and when it changes
    applyTheme(currentTheme);
  }, [currentTheme]);

  const setTheme = (themeName: string) => {
    const theme = themes.find(t => t.name === themeName);
    if (theme) {
      setCurrentTheme(theme);
      localStorage.setItem(STORAGE_KEY, themeName);
    }
  };

  return (
    <ThemeContext.Provider value={{ currentTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
