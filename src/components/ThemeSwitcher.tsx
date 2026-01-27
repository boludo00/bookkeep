import { Palette } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTheme, themes } from '@/contexts/ThemeContext';

export function ThemeSwitcher() {
  const { currentTheme, setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-card/50 text-foreground hover:bg-card hover:border-primary/30 transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-2 focus:ring-offset-background"
          aria-label="Choose theme"
        >
          <Palette className="h-5 w-5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-56 p-2 bg-card border-border/50 rounded-xl shadow-2xl"
      >
        <DropdownMenuLabel className="flex items-center gap-2 px-2 py-1.5 text-foreground">
          <Palette className="h-4 w-4" />
          Choose Theme
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="my-2 bg-border/50" />
        <DropdownMenuRadioGroup value={currentTheme.name} onValueChange={setTheme}>
          {themes.map((theme) => (
            <DropdownMenuRadioItem
              key={theme.name}
              value={theme.name}
              className="rounded-lg cursor-pointer focus:bg-primary/10 py-2.5"
            >
              <div className="flex items-center justify-between w-full">
                <span className="font-medium">{theme.label}</span>
                <div className="flex items-center gap-1 ml-3">
                  <div
                    className="h-4 w-4 rounded-full border border-border/50"
                    style={{ backgroundColor: `hsl(${theme.colors.primary})` }}
                    aria-hidden="true"
                  />
                  <div
                    className="h-4 w-4 rounded-full border border-border/50"
                    style={{ backgroundColor: `hsl(${theme.colors.accent})` }}
                    aria-hidden="true"
                  />
                </div>
              </div>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
