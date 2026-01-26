import { useState } from 'react';
import { Save, TestTube, CheckCircle, XCircle, Eye, EyeOff, Plus, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { downloadSettingsApi, type ProwlarrServer, type ProwlarrIndexer } from '@/lib/api';

interface ProwlarrForm {
  name: string;
  host: string;
  port: number;
  use_ssl: boolean;
  api_key: string;
  url_base: string;
  enabled: boolean;
  is_default: boolean;
  indexer_ids: number[];
}

export default function ProwlarrSettings() {
  const [showModal, setShowModal] = useState(false);
  const [editingServer, setEditingServer] = useState<ProwlarrServer | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; indexers?: any[]; total_indexers?: number; error?: string } | null>(null);
  const [availableIndexers, setAvailableIndexers] = useState<ProwlarrIndexer[]>([]);

  const [form, setForm] = useState<ProwlarrForm>({
    name: '',
    host: '',
    port: 9696,
    use_ssl: false,
    api_key: '',
    url_base: '',
    enabled: true,
    is_default: false,
    indexer_ids: [],
  });

  const queryClient = useQueryClient();

  // Fetch Prowlarr servers
  const { data: servers = [] } = useQuery({
    queryKey: ['prowlarr-servers'],
    queryFn: () => downloadSettingsApi.getProwlarrServers(),
  });

  // Create/Update mutation
  const saveServerMutation = useMutation({
    mutationFn: async (data: ProwlarrForm) => {
      if (editingServer) {
        return downloadSettingsApi.updateProwlarrServer(editingServer.id, data);
      } else {
        return downloadSettingsApi.createProwlarrServer(data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prowlarr-servers'] });
      toast.success(editingServer ? 'Prowlarr server updated!' : 'Prowlarr server added!');
      setShowModal(false);
      resetForm();
    },
    onError: (error: Error) => {
      toast.error('Failed to save Prowlarr server', {
        description: error.message,
      });
    },
  });

  // Delete mutation
  const deleteServerMutation = useMutation({
    mutationFn: (id: number) => downloadSettingsApi.deleteProwlarrServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prowlarr-servers'] });
      toast.success('Prowlarr server deleted');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete server', {
        description: error.message,
      });
    },
  });

  const resetForm = () => {
    setForm({
      name: '',
      host: '',
      port: 9696,
      use_ssl: false,
      api_key: '',
      url_base: '',
      enabled: true,
      is_default: false,
      indexer_ids: [],
    });
    setEditingServer(null);
    setTestResult(null);
    setAvailableIndexers([]);
  };

  const handleAdd = () => {
    resetForm();
    setShowModal(true);
  };

  const handleEdit = async (server: ProwlarrServer) => {
    setEditingServer(server);
    setShowModal(true);

    // Load available indexers for this server
    try {
      const result = await downloadSettingsApi.getProwlarrIndexers(server.id);
      const indexers = result.indexers || [];
      setAvailableIndexers(indexers);

      // If no indexers were previously saved, select all by default
      const savedIndexerIds = server.indexer_ids || [];
      const indexerIds = savedIndexerIds.length > 0
        ? savedIndexerIds
        : indexers.map((idx: ProwlarrIndexer) => idx.id);

      setForm({
        name: server.name,
        host: server.host,
        port: server.port,
        use_ssl: server.use_ssl,
        api_key: server.api_key,
        url_base: server.url_base || '',
        enabled: server.enabled,
        is_default: server.is_default,
        indexer_ids: indexerIds,
      });
    } catch (error) {
      console.error('Failed to load indexers:', error);
      // Still set the form even if indexers fail to load
      setForm({
        name: server.name,
        host: server.host,
        port: server.port,
        use_ssl: server.use_ssl,
        api_key: server.api_key,
        url_base: server.url_base || '',
        enabled: server.enabled,
        is_default: server.is_default,
        indexer_ids: server.indexer_ids || [],
      });
    }
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);

    try {
      const result = await downloadSettingsApi.testProwlarrConnection({
        host: form.host,
        port: form.port,
        use_ssl: form.use_ssl,
        api_key: form.api_key,
        url_base: form.url_base || undefined,
      });

      setTestResult(result);

      if (result.success) {
        toast.success('Connection successful!');
        // Store the full indexer data for selection
        if (result.indexers) {
          const indexers = result.indexers.map((idx: any) => ({
            id: idx.id,
            name: idx.name,
            protocol: idx.protocol,
            privacy: idx.privacy,
            enabled: idx.enable !== false,
          }));
          setAvailableIndexers(indexers);
          // Auto-check all indexers by default
          setForm(prev => ({
            ...prev,
            indexer_ids: indexers.map((idx: ProwlarrIndexer) => idx.id),
          }));
        }
      } else {
        toast.error('Connection failed', {
          description: result.error,
        });
      }
    } catch (error: any) {
      setTestResult({ success: false, error: error.message });
      toast.error('Connection test failed', {
        description: error.message,
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSave = () => {
    if (!form.name || !form.host || !form.api_key) {
      toast.error('Please fill in all required fields');
      return;
    }

    if (availableIndexers.length > 0 && form.indexer_ids.length === 0) {
      toast.error('Please select at least one indexer');
      return;
    }

    saveServerMutation.mutate(form);
  };

  return (
    <>
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Prowlarr</CardTitle>
          <CardDescription>
            Configure your Prowlarr server for searching releases. Prowlarr is used to search across multiple indexers for books.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing servers */}
          {servers.map((server: ProwlarrServer) => (
            <div
              key={server.id}
              className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/50"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-foreground">{server.name}</span>
                  {server.is_default && (
                    <Badge variant="secondary" className="text-xs">Default</Badge>
                  )}
                  {!server.enabled && (
                    <Badge variant="outline" className="text-xs">Disabled</Badge>
                  )}
                  {server.indexer_ids && server.indexer_ids.length > 0 && (
                    <Badge variant="outline" className="text-xs">
                      {server.indexer_ids.length} indexer{server.indexer_ids.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {server.use_ssl ? 'https' : 'http'}://{server.host}:{server.port}{server.url_base ? `/${server.url_base}` : ''}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleEdit(server)}
                >
                  <Edit className="h-4 w-4 mr-1" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => deleteServerMutation.mutate(server.id)}
                  disabled={deleteServerMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}

          {/* Add new server button */}
          <button
            onClick={handleAdd}
            className="w-full p-4 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-secondary/50 transition-colors flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-5 w-5" />
            Add Prowlarr Server
          </button>
        </CardContent>
      </Card>

      {/* Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingServer ? 'Edit Prowlarr Server' : 'Add Prowlarr Server'}
            </DialogTitle>
            <DialogDescription>
              Configure your Prowlarr server connection
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="prowlarr-name" className="text-foreground">Name *</Label>
              <Input
                id="prowlarr-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., Main Prowlarr"
                className="bg-secondary border-border"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="prowlarr-host" className="text-foreground">Host *</Label>
              <Input
                id="prowlarr-host"
                value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="prowlarr.example.com or 192.168.1.100"
                className="bg-secondary border-border"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="prowlarr-port" className="text-foreground">Port *</Label>
                <Input
                  id="prowlarr-port"
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) })}
                  className="bg-secondary border-border"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="prowlarr-url-base" className="text-foreground">URL Base</Label>
                <Input
                  id="prowlarr-url-base"
                  value={form.url_base}
                  onChange={(e) => setForm({ ...form, url_base: e.target.value })}
                  placeholder="/prowlarr"
                  className="bg-secondary border-border"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="prowlarr-api-key" className="text-foreground">API Key *</Label>
              <div className="relative">
                <Input
                  id="prowlarr-api-key"
                  type={showApiKey ? "text" : "password"}
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  className="bg-secondary border-border pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3"
                  onClick={() => setShowApiKey(!showApiKey)}
                >
                  {showApiKey ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="prowlarr-ssl"
                checked={form.use_ssl}
                onCheckedChange={(checked) =>
                  setForm({ ...form, use_ssl: checked === true })
                }
              />
              <Label htmlFor="prowlarr-ssl" className="font-normal cursor-pointer">
                Use SSL (HTTPS)
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="prowlarr-enabled"
                checked={form.enabled}
                onCheckedChange={(checked) =>
                  setForm({ ...form, enabled: checked === true })
                }
              />
              <Label htmlFor="prowlarr-enabled" className="font-normal cursor-pointer">
                Enabled
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="prowlarr-default"
                checked={form.is_default}
                onCheckedChange={(checked) =>
                  setForm({ ...form, is_default: checked === true })
                }
              />
              <Label htmlFor="prowlarr-default" className="font-normal cursor-pointer">
                Default Server
              </Label>
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={testingConnection || !form.host || !form.api_key}
              className="w-full"
            >
              <TestTube className="h-4 w-4 mr-2" />
              {testingConnection ? 'Testing...' : 'Test Connection'}
            </Button>

            {testResult && (
              <div className={`p-3 rounded-lg ${testResult.success ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                <div className="flex items-center gap-2">
                  {testResult.success ? (
                    <CheckCircle className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <span className="text-sm">
                    {testResult.success
                      ? `Connected! Found ${testResult.total_indexers || 0} indexers`
                      : testResult.error}
                  </span>
                </div>
              </div>
            )}

            {/* Indexer Selection - shown after successful test or when editing */}
            {availableIndexers.length > 0 && (
              <div className="space-y-3 p-4 border border-border rounded-lg bg-secondary/30">
                <div className="flex items-center justify-between">
                  <Label className="text-foreground font-medium">Indexers to Search</Label>
                  <span className="text-xs text-muted-foreground">
                    {form.indexer_ids.length === 0
                      ? 'All indexers'
                      : `${form.indexer_ids.length} selected`}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Select which indexers to use for book searches. Only checked indexers will be searched.
                </p>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {availableIndexers.map((indexer) => (
                    <div key={indexer.id} className="flex items-center space-x-2">
                      <Checkbox
                        id={`indexer-${indexer.id}`}
                        checked={form.indexer_ids.includes(indexer.id)}
                        onCheckedChange={(checked) => {
                          if (checked) {
                            setForm({ ...form, indexer_ids: [...form.indexer_ids, indexer.id] });
                          } else {
                            setForm({ ...form, indexer_ids: form.indexer_ids.filter(id => id !== indexer.id) });
                          }
                        }}
                      />
                      <Label
                        htmlFor={`indexer-${indexer.id}`}
                        className="font-normal cursor-pointer flex items-center gap-2"
                      >
                        <span>{indexer.name}</span>
                        <Badge variant="outline" className="text-xs">
                          {indexer.protocol}
                        </Badge>
                        {!indexer.enabled && (
                          <Badge variant="secondary" className="text-xs">
                            Disabled
                          </Badge>
                        )}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4 border-t border-border">
              <Button
                variant="outline"
                onClick={() => {
                  setShowModal(false);
                  resetForm();
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSave}
                disabled={saveServerMutation.isPending}
              >
                <Save className="h-4 w-4 mr-2" />
                {saveServerMutation.isPending ? 'Saving...' : editingServer ? 'Update' : 'Add Server'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
