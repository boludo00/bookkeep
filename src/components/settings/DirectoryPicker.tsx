import { useState } from 'react';
import { Folder, FolderOpen, ChevronUp, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTrigger, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { settingsApi } from '@/lib/api';

interface DirectoryPickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  id?: string;
}

export default function DirectoryPicker({ value, onChange, placeholder, id }: DirectoryPickerProps) {
  const [open, setOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState('/');

  const { data, isLoading } = useQuery({
    queryKey: ['browse-directories', browsePath],
    queryFn: () => settingsApi.browseDirectories(browsePath),
    enabled: open,
  });

  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      setBrowsePath(value || '/');
    }
    setOpen(isOpen);
  };

  const handleSelect = () => {
    if (data?.current_path) {
      onChange(data.current_path);
      setOpen(false);
    }
  };

  return (
    <div className="flex gap-2">
      <Input
        id={id}
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-secondary border-border font-mono text-sm"
      />
      <Dialog open={open} onOpenChange={handleOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" size="icon" className="shrink-0 border-border">
            <Folder className="h-4 w-4" />
          </Button>
        </DialogTrigger>
        <DialogContent className="p-0 gap-0">
          <DialogHeader className="border-b border-border px-4 py-3">
            <DialogTitle className="text-sm">Browse Directories</DialogTitle>
            <DialogDescription className="font-mono text-xs truncate" title={data?.current_path}>
              {data?.current_path ?? browsePath}
            </DialogDescription>
          </DialogHeader>

          {data?.error ? (
            <p className="px-4 py-4 text-sm text-destructive">{data.error}</p>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ScrollArea className="max-h-72">
              <div className="p-1">
                {data?.parent_path !== null && data?.parent_path !== undefined && (
                  <button
                    type="button"
                    onClick={() => setBrowsePath(data.parent_path!)}
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-2.5 text-sm hover:bg-accent"
                  >
                    <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">..</span>
                  </button>
                )}
                {data?.directories.map((dir) => (
                  <button
                    key={dir.path}
                    type="button"
                    onClick={() => setBrowsePath(dir.path)}
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-2.5 text-sm hover:bg-accent"
                  >
                    <FolderOpen className="h-4 w-4 text-muted-foreground" />
                    <span className="truncate">{dir.name}</span>
                  </button>
                ))}
                {data?.directories.length === 0 && !data?.parent_path && (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                    No subdirectories
                  </p>
                )}
              </div>
            </ScrollArea>
          )}

          <div className="border-t border-border p-3">
            <Button size="sm" className="w-full" onClick={handleSelect} disabled={isLoading || !!data?.error}>
              Select this directory
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
