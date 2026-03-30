import { useState, useEffect } from 'react';
import { Save, TestTube, CheckCircle, XCircle, Eye, EyeOff, Download, Globe, Lock, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { directDownloadApi } from '@/lib/api';

interface DirectDownloadForm {
  enabled: boolean;
  annas_archive_enabled: boolean;
  annas_archive_mirror: string;
  annas_archive_language: string;
  zlibrary_enabled: boolean;
  zlibrary_email: string;
  zlibrary_password: string;
  zlibrary_domain: string;
  requests_per_minute: number;
  flaresolverr_url: string;
}

export default function DirectDownloadSettings() {
  const [showPassword, setShowPassword] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testingFlaresolverr, setTestingFlaresolverr] = useState(false);
  const [flaresolverrResult, setFlaresolverrResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    providers_count: number;
    providers_status: Record<string, boolean>;
    message?: string;
  } | null>(null);

  const [form, setForm] = useState<DirectDownloadForm>({
    enabled: false,
    annas_archive_enabled: true,
    annas_archive_mirror: '',
    annas_archive_language: '',
    zlibrary_enabled: false,
    zlibrary_email: '',
    zlibrary_password: '',
    zlibrary_domain: '',
    requests_per_minute: 10,
    flaresolverr_url: '',
  });

  const queryClient = useQueryClient();

  // Fetch current settings
  const { data: settings, isLoading } = useQuery({
    queryKey: ['direct-download-settings'],
    queryFn: () => directDownloadApi.getSettings(),
  });

  // Update form when settings are fetched
  useEffect(() => {
    if (settings) {
      setForm({
        enabled: settings.enabled,
        annas_archive_enabled: settings.annas_archive_enabled,
        annas_archive_mirror: settings.annas_archive_mirror || '',
        annas_archive_language: settings.annas_archive_language || '',
        zlibrary_enabled: settings.zlibrary_enabled,
        zlibrary_email: settings.zlibrary_email || '',
        zlibrary_password: '', // Never populate from server
        zlibrary_domain: settings.zlibrary_domain || '',
        requests_per_minute: settings.requests_per_minute,
        flaresolverr_url: settings.flaresolverr_url || '',
      });
    }
  }, [settings]);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (data: DirectDownloadForm) => directDownloadApi.updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['direct-download-settings'] });
      toast.success('Settings saved!');
    },
    onError: (error: Error) => {
      toast.error('Failed to save settings', { description: error.message });
    },
  });

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);

    try {
      const result = await directDownloadApi.testConnection();
      setTestResult(result);

      if (result.success) {
        toast.success(result.message || 'Connection successful!');
      } else {
        toast.error(result.message || 'Connection failed');
      }
    } catch (error: any) {
      setTestResult({ success: false, providers_count: 0, providers_status: {}, message: error.message });
      toast.error('Test failed', { description: error.message });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSave = () => {
    saveMutation.mutate(form);
  };

  const handleTestFlaresolverr = async () => {
    if (!form.flaresolverr_url) {
      toast.error('Please enter a FlareSolverr URL first');
      return;
    }

    setTestingFlaresolverr(true);
    setFlaresolverrResult(null);

    try {
      const result = await directDownloadApi.testFlaresolverr(form.flaresolverr_url);
      setFlaresolverrResult(result);

      if (result.success) {
        toast.success(result.message || 'FlareSolverr connected!');
      } else {
        toast.error(result.message || 'FlareSolverr connection failed');
      }
    } catch (error: any) {
      setFlaresolverrResult({ success: false, message: error.message });
      toast.error('Test failed', { description: error.message });
    } finally {
      setTestingFlaresolverr(false);
    }
  };

  if (isLoading) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/4"></div>
            <div className="h-10 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/10">
              <Download className="h-5 w-5 text-green-500" />
            </div>
            <div>
              <CardTitle className="text-foreground">Direct Downloads</CardTitle>
              <CardDescription>
                Download books directly from web sources without torrent/usenet clients
              </CardDescription>
            </div>
          </div>
          {form.enabled && (
            <Badge variant="outline" className="border-green-500/40 text-green-500">
              Enabled
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Master Enable Toggle */}
        <div className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 border border-border">
          <div className="space-y-1">
            <Label className="text-foreground font-medium">Enable Direct Downloads</Label>
            <p className="text-sm text-muted-foreground">
              Search and download from direct sources alongside Prowlarr results
            </p>
          </div>
          <Switch
            checked={form.enabled}
            onCheckedChange={(checked) => setForm({ ...form, enabled: checked })}
          />
        </div>

        {form.enabled && (
          <>
            {/* Anna's Archive Section */}
            <div className="space-y-4 p-4 rounded-lg border border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Globe className="h-5 w-5 text-blue-500" />
                  <div>
                    <Label className="text-foreground font-medium">Anna's Archive</Label>
                    <p className="text-sm text-muted-foreground">
                      Shadow library with millions of books (no account needed)
                    </p>
                  </div>
                </div>
                <Switch
                  checked={form.annas_archive_enabled}
                  onCheckedChange={(checked) =>
                    setForm({ ...form, annas_archive_enabled: checked })
                  }
                />
              </div>

              {form.annas_archive_enabled && (
                <div className="space-y-2 pt-2 pl-8">
                  <Label htmlFor="annas-mirror" className="text-muted-foreground text-sm">
                    Custom Mirror (optional)
                  </Label>
                  <Input
                    id="annas-mirror"
                    value={form.annas_archive_mirror}
                    onChange={(e) => setForm({ ...form, annas_archive_mirror: e.target.value })}
                    placeholder="https://annas-archive.org"
                    className="bg-secondary border-border"
                  />
                  <p className="text-xs text-muted-foreground">
                    Leave blank to use the default mirror
                  </p>

                  <div className="space-y-2 pt-2">
                    <Label htmlFor="annas-lang" className="text-muted-foreground text-sm">
                      Language Filter (optional)
                    </Label>
                    <Input
                      id="annas-lang"
                      value={form.annas_archive_language}
                      onChange={(e) => setForm({ ...form, annas_archive_language: e.target.value })}
                      placeholder="e.g. fr, en, es"
                      className="bg-secondary border-border"
                    />
                    <p className="text-xs text-muted-foreground">
                      Use ISO 639-1 language codes (e.g., 'fr' for French, 'en' for English)
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Z-Library Section */}
            <div className="space-y-4 p-4 rounded-lg border border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Lock className="h-5 w-5 text-purple-500" />
                  <div>
                    <Label className="text-foreground font-medium">Z-Library</Label>
                    <p className="text-sm text-muted-foreground">
                      Requires a free account for authentication
                    </p>
                  </div>
                </div>
                <Switch
                  checked={form.zlibrary_enabled}
                  onCheckedChange={(checked) =>
                    setForm({ ...form, zlibrary_enabled: checked })
                  }
                />
              </div>

              {form.zlibrary_enabled && (
                <div className="space-y-4 pt-2 pl-8">
                  <div className="space-y-2">
                    <Label htmlFor="zlib-email" className="text-muted-foreground text-sm">
                      Email
                    </Label>
                    <Input
                      id="zlib-email"
                      type="email"
                      value={form.zlibrary_email}
                      onChange={(e) => setForm({ ...form, zlibrary_email: e.target.value })}
                      placeholder="your@email.com"
                      className="bg-secondary border-border"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="zlib-password" className="text-muted-foreground text-sm">
                      Password
                    </Label>
                    <div className="relative">
                      <Input
                        id="zlib-password"
                        type={showPassword ? 'text' : 'password'}
                        value={form.zlibrary_password}
                        onChange={(e) => setForm({ ...form, zlibrary_password: e.target.value })}
                        placeholder={settings?.zlibrary_password_set ? '••••••••' : 'Enter password'}
                        className="bg-secondary border-border pr-10"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                        onClick={() => setShowPassword(!showPassword)}
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <Eye className="h-4 w-4 text-muted-foreground" />
                        )}
                      </Button>
                    </div>
                    {settings?.zlibrary_password_set && (
                      <p className="text-xs text-muted-foreground">
                        Password is set. Leave blank to keep current password.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="zlib-domain" className="text-muted-foreground text-sm">
                      Custom Domain (optional)
                    </Label>
                    <Input
                      id="zlib-domain"
                      value={form.zlibrary_domain}
                      onChange={(e) => setForm({ ...form, zlibrary_domain: e.target.value })}
                      placeholder="singlelogin.re"
                      className="bg-secondary border-border"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Cloudflare Bypass (FlareSolverr) */}
            <div className="space-y-4 p-4 rounded-lg border border-border">
              <div className="flex items-center gap-3">
                <Shield className="h-5 w-5 text-amber-500" />
                <div>
                  <Label className="text-foreground font-medium">Cloudflare Bypass</Label>
                  <p className="text-sm text-muted-foreground">
                    Optional: Use FlareSolverr to bypass Cloudflare protection on source sites
                  </p>
                </div>
              </div>

              <div className="space-y-2 pt-2 pl-8">
                <Label htmlFor="flaresolverr-url" className="text-muted-foreground text-sm">
                  FlareSolverr URL
                </Label>
                <div className="flex gap-2">
                  <Input
                    id="flaresolverr-url"
                    value={form.flaresolverr_url}
                    onChange={(e) => setForm({ ...form, flaresolverr_url: e.target.value })}
                    placeholder="http://flaresolverr:8191"
                    className="bg-secondary border-border"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleTestFlaresolverr}
                    disabled={testingFlaresolverr || !form.flaresolverr_url}
                    className="shrink-0"
                  >
                    <TestTube className="h-4 w-4 mr-1" />
                    {testingFlaresolverr ? 'Testing...' : 'Test'}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Leave blank to disable. Run FlareSolverr as a Docker sidecar for Cloudflare bypass.
                </p>
                {flaresolverrResult && (
                  <div className="flex items-center gap-2 text-sm mt-1">
                    {flaresolverrResult.success ? (
                      <CheckCircle className="h-4 w-4 text-green-500" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className={flaresolverrResult.success ? 'text-green-500' : 'text-red-500'}>
                      {flaresolverrResult.message}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Rate Limiting */}
            <div className="space-y-2">
              <Label htmlFor="rate-limit" className="text-foreground">
                Requests per Minute
              </Label>
              <Input
                id="rate-limit"
                type="number"
                value={form.requests_per_minute}
                onChange={(e) =>
                  setForm({ ...form, requests_per_minute: parseInt(e.target.value) || 10 })
                }
                min={1}
                max={60}
                className="bg-secondary border-border w-32"
              />
              <p className="text-xs text-muted-foreground">
                Limit requests to avoid rate limiting (recommended: 10)
              </p>
            </div>
          </>
        )}

        {/* Test Result */}
        {testResult && (
          <div
            className={`p-4 rounded-lg ${
              testResult.success
                ? 'bg-green-500/10 border border-green-500/30'
                : 'bg-red-500/10 border border-red-500/30'
            }`}
          >
            <div className="flex items-center gap-2">
              {testResult.success ? (
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              <span className={testResult.success ? 'text-green-500' : 'text-red-500'}>
                {testResult.message}
              </span>
            </div>
            {testResult.success && Object.keys(testResult.providers_status).length > 0 && (
              <div className="mt-2 pl-7 space-y-1">
                {Object.entries(testResult.providers_status).map(([provider, status]) => (
                  <div key={provider} className="flex items-center gap-2 text-sm">
                    {status ? (
                      <CheckCircle className="h-4 w-4 text-green-500" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-muted-foreground capitalize">
                      {provider.replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2">
          <Button
            variant="outline"
            onClick={handleTestConnection}
            disabled={testingConnection || !form.enabled}
          >
            <TestTube className="h-4 w-4 mr-2" />
            {testingConnection ? 'Testing...' : 'Test Connection'}
          </Button>

          <Button onClick={handleSave} disabled={saveMutation.isPending}>
            <Save className="h-4 w-4 mr-2" />
            {saveMutation.isPending ? 'Saving...' : 'Save Settings'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
