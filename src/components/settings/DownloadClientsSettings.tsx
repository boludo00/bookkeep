import { useState } from 'react';
import { Save, TestTube, CheckCircle, XCircle, Eye, EyeOff, Plus, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { downloadSettingsApi, type DownloadClient } from '@/lib/api';

interface DownloadClientForm {
  name: string;
  type: string;
  protocol: string;
  host: string;
  port: number;
  use_ssl: boolean;
  username: string;
  password: string;
  enabled: boolean;
  priority: number;
  category: string;
  ebook_category: string;
  audiobook_category: string;
}

export default function DownloadClientsSettings() {
  const [showModal, setShowModal] = useState(false);
  const [editingClient, setEditingClient] = useState<DownloadClient | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; version?: string; api_version?: string; error?: string } | null>(null);

  const [form, setForm] = useState<DownloadClientForm>({
    name: '',
    type: 'qbittorrent',
    protocol: 'torrent',
    host: '',
    port: 8080,
    use_ssl: false,
    username: '',
    password: '',
    enabled: true,
    priority: 0,
    category: 'books',
    ebook_category: 'books-ebook',
    audiobook_category: 'books-audiobook',
  });

  const queryClient = useQueryClient();

  // Fetch download clients
  const { data: clients = [] } = useQuery({
    queryKey: ['download-clients'],
    queryFn: () => downloadSettingsApi.getDownloadClients(),
  });

  // Create/Update mutation
  const saveClientMutation = useMutation({
    mutationFn: async (data: DownloadClientForm) => {
      if (editingClient) {
        return downloadSettingsApi.updateDownloadClient(editingClient.id, data);
      } else {
        return downloadSettingsApi.createDownloadClient(data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['download-clients'] });
      toast.success(editingClient ? 'Download client updated!' : 'Download client added!');
      setShowModal(false);
      resetForm();
    },
    onError: (error: Error) => {
      toast.error('Failed to save download client', {
        description: error.message,
      });
    },
  });

  // Delete mutation
  const deleteClientMutation = useMutation({
    mutationFn: (id: number) => downloadSettingsApi.deleteDownloadClient(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['download-clients'] });
      toast.success('Download client deleted');
    },
    onError: (error: Error) => {
      toast.error('Failed to delete client', {
        description: error.message,
      });
    },
  });

  const resetForm = () => {
    setForm({
      name: '',
      type: 'qbittorrent',
      protocol: 'torrent',
      host: '',
      port: 8080,
      use_ssl: false,
      username: '',
      password: '',
      enabled: true,
      priority: 0,
      category: 'books',
      ebook_category: 'books-ebook',
      audiobook_category: 'books-audiobook',
    });
    setEditingClient(null);
    setTestResult(null);
  };

  const handleAdd = () => {
    resetForm();
    setShowModal(true);
  };

  const handleEdit = (client: DownloadClient) => {
    setEditingClient(client);
    setForm({
      name: client.name,
      type: client.type,
      protocol: client.protocol,
      host: client.host,
      port: client.port,
      use_ssl: client.use_ssl,
      username: client.username || '',
      password: '', // Don't populate password for security
      enabled: client.enabled,
      priority: client.priority,
      category: client.category || 'books',
      ebook_category: client.ebook_category || 'books-ebook',
      audiobook_category: client.audiobook_category || 'books-audiobook',
    });
    setShowModal(true);
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);

    try {
      const result = await downloadSettingsApi.testDownloadClient({
        type: form.type,
        protocol: form.protocol,
        host: form.host,
        port: form.port,
        use_ssl: form.use_ssl,
        username: form.username || undefined,
        password: form.password || undefined,
        api_key: form.password || undefined, // For Sabnzbd, password field contains API key
      });

      setTestResult(result);

      if (result.success) {
        toast.success('Connection successful!');
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
    if (!form.name || !form.host) {
      toast.error('Please fill in all required fields');
      return;
    }

    // Don't send empty password for updates
    const data = { ...form };
    if (editingClient && !data.password) {
      delete (data as any).password;
    }

    saveClientMutation.mutate(data);
  };

  const handleTypeChange = (type: string) => {
    // Update default port based on type
    let newPort = form.port;
    let newProtocol = form.protocol;

    if (type === 'qbittorrent') {
      newPort = 8080;
      newProtocol = 'torrent';
    } else if (type === 'nzbget') {
      newPort = 6789;
      newProtocol = 'usenet';
    } else if (type === 'sabnzbd') {
      newPort = 8080;
      newProtocol = 'usenet';
    }

    setForm({ ...form, type, port: newPort, protocol: newProtocol });
  };

  const getClientTypeLabel = (type: string) => {
    switch (type) {
      case 'qbittorrent':
        return 'qBittorrent';
      case 'nzbget':
        return 'NZBGet';
      case 'sabnzbd':
        return 'Sabnzbd';
      default:
        return type;
    }
  };

  return (
    <>
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Download Clients</CardTitle>
          <CardDescription>
            Configure your download clients for torrents and usenet. Higher priority clients will be used first.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing clients */}
          {clients.map((client: DownloadClient) => (
            <div
              key={client.id}
              className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/50"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-foreground">{client.name}</span>
                  <Badge variant="secondary" className="text-xs">{getClientTypeLabel(client.type)}</Badge>
                  <Badge variant="outline" className="text-xs">{client.protocol}</Badge>
                  {!client.enabled && (
                    <Badge variant="outline" className="text-xs">Disabled</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {client.use_ssl ? 'https' : 'http'}://{client.host}:{client.port}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Priority: {client.priority} | Category: {client.category || 'None'}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleEdit(client)}
                >
                  <Edit className="h-4 w-4 mr-1" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => deleteClientMutation.mutate(client.id)}
                  disabled={deleteClientMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}

          {/* Add new client button */}
          <button
            onClick={handleAdd}
            className="w-full p-4 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-secondary/50 transition-colors flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-5 w-5" />
            Add Download Client
          </button>
        </CardContent>
      </Card>

      {/* Modal */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingClient ? 'Edit Download Client' : 'Add Download Client'}
            </DialogTitle>
            <DialogDescription>
              Configure your download client connection. For usenet clients, you'll need the API key from your client's settings.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="client-name" className="text-foreground">Name *</Label>
              <Input
                id="client-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., Primary qBittorrent"
                className="bg-secondary border-border"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-type" className="text-foreground">Client Type *</Label>
              <Select value={form.type} onValueChange={handleTypeChange}>
                <SelectTrigger className="bg-secondary border-border">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="qbittorrent">qBittorrent (Torrent)</SelectItem>
                  <SelectItem value="nzbget">NZBGet (Usenet)</SelectItem>
                  <SelectItem value="sabnzbd">Sabnzbd (Usenet)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-host" className="text-foreground">Host *</Label>
              <Input
                id="client-host"
                value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="localhost or 192.168.1.100"
                className="bg-secondary border-border"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="client-port" className="text-foreground">Port *</Label>
                <Input
                  id="client-port"
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) })}
                  className="bg-secondary border-border"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="client-priority" className="text-foreground">Priority</Label>
                <Input
                  id="client-priority"
                  type="number"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) })}
                  className="bg-secondary border-border"
                />
              </div>
            </div>

            {form.type === 'qbittorrent' && (
              <div className="space-y-2">
                <Label htmlFor="client-username" className="text-foreground">Username</Label>
                <Input
                  id="client-username"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  placeholder="admin"
                  className="bg-secondary border-border"
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="client-password" className="text-foreground">
                {form.type === 'sabnzbd' ? 'API Key' : form.type === 'nzbget' ? 'API Key' : 'Password'} {editingClient ? '(leave blank to keep current)' : ''}
              </Label>
              <div className="relative">
                <Input
                  id="client-password"
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder={
                    form.type === 'nzbget'
                      ? 'ControlPassword from nzbget.conf'
                      : form.type === 'sabnzbd'
                        ? 'API Key from Sabnzbd settings'
                        : ''
                  }
                  className="bg-secondary border-border pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
              {form.type === 'nzbget' && (
                <p className="text-xs text-muted-foreground">
                  Use the ControlPassword from your nzbget.conf file
                </p>
              )}
              {form.type === 'sabnzbd' && (
                <p className="text-xs text-muted-foreground">
                  Find your API key in Sabnzbd settings under General → Security
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="client-category" className="text-foreground">Default Category (Legacy)</Label>
              <Input
                id="client-category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                placeholder="books"
                className="bg-secondary border-border"
              />
              <p className="text-xs text-muted-foreground">
                Fallback category if format-specific categories not set
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ebook-category" className="text-foreground">Ebook Category</Label>
                <Input
                  id="ebook-category"
                  value={form.ebook_category}
                  onChange={(e) => setForm({ ...form, ebook_category: e.target.value })}
                  placeholder="books-ebook"
                  className="bg-secondary border-border"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="audiobook-category" className="text-foreground">Audiobook Category</Label>
                <Input
                  id="audiobook-category"
                  value={form.audiobook_category}
                  onChange={(e) => setForm({ ...form, audiobook_category: e.target.value })}
                  placeholder="books-audiobook"
                  className="bg-secondary border-border"
                />
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="client-ssl"
                checked={form.use_ssl}
                onCheckedChange={(checked) =>
                  setForm({ ...form, use_ssl: checked === true })
                }
              />
              <Label htmlFor="client-ssl" className="font-normal cursor-pointer">
                Use SSL (HTTPS)
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="client-enabled"
                checked={form.enabled}
                onCheckedChange={(checked) =>
                  setForm({ ...form, enabled: checked === true })
                }
              />
              <Label htmlFor="client-enabled" className="font-normal cursor-pointer">
                Enabled
              </Label>
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={testingConnection || !form.host}
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
                      ? `Connected! ${testResult.version ? `Version: ${testResult.version}` : ''}`
                      : testResult.error}
                  </span>
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
                disabled={saveClientMutation.isPending}
              >
                <Save className="h-4 w-4 mr-2" />
                {saveClientMutation.isPending ? 'Saving...' : editingClient ? 'Update' : 'Add Client'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
