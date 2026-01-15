import { useState } from 'react';
import { Check, X, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { requestsApi } from '@/lib/api';
import { transformHardcoverBook } from '@/lib/hardcover';
import type { BookRequest } from '@/types/book';

export default function Admin() {
  const queryClient = useQueryClient();
  
  const { data: requestsData = [] } = useQuery({
    queryKey: ['requests', 'admin'],
    queryFn: () => requestsApi.getAll(0, 100),
  });

  const updateRequestMutation = useMutation({
    mutationFn: ({ id, update }: { id: number; update: { status?: string; admin_notes?: string } }) =>
      requestsApi.update(id, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });

  // Filter out requests without books to prevent UI issues
  const requests: BookRequest[] = requestsData
    .filter((req: any) => req.book) // Only include requests with associated books
    .map((req: any) => ({
      id: String(req.id),
      bookId: String(req.book?.hardcover_id || req.book_id),
      book: {
        id: String(req.book.id),
        title: req.book.title || 'Unknown Title',
        author: req.book.author || 'Unknown Author',
        cover: req.book.cover_url || '/placeholder.svg',
        description: req.book.description || '',
        publishedDate: req.book.published_date || '',
        genres: req.book.genres ? (typeof req.book.genres === 'string' ? req.book.genres.split(',') : req.book.genres) : [],
        rating: req.book.rating || 0,
        series: req.book.series,
        seriesPosition: req.book.series_position,
        hardcoverId: req.book.hardcover_id,
        hardcoverSlug: req.book.hardcover_slug,
        isbn: req.book.isbn,
        pageCount: req.book.page_count,
      },
      userId: String(req.user_id),
      userName: req.user?.username || req.user?.full_name || 'Unknown User',
      format: req.format,
      status: req.status,
      notes: req.notes,
      adminNotes: req.admin_notes,
      createdAt: req.created_at,
      updatedAt: req.updated_at,
    }));
  const [noteDialog, setNoteDialog] = useState<{ open: boolean; request: BookRequest | null }>({
    open: false,
    request: null,
  });
  const [adminNote, setAdminNote] = useState('');

  const pendingRequests = requests.filter((r) => r.status === 'requested');
  const processedRequests = requests.filter((r) => r.status !== 'requested');

  const handleApprove = (id: string) => {
    updateRequestMutation.mutate(
      { id: Number(id), update: { status: 'approved' } },
      {
        onSuccess: () => {
          toast.success('Request approved', {
            description: 'The request will be sent to Readarr for processing.',
          });
        },
        onError: () => {
          toast.error('Failed to approve request');
        },
      }
    );
  };

  const handleDeny = (id: string) => {
    updateRequestMutation.mutate(
      { id: Number(id), update: { status: 'denied' } },
      {
        onSuccess: () => {
          toast.info('Request denied');
        },
        onError: () => {
          toast.error('Failed to deny request');
        },
      }
    );
  };

  const handleAddNote = () => {
    if (noteDialog.request && adminNote) {
      updateRequestMutation.mutate(
        { id: Number(noteDialog.request.id), update: { admin_notes: adminNote } },
        {
          onSuccess: () => {
            toast.success('Note added');
            setNoteDialog({ open: false, request: null });
            setAdminNote('');
          },
          onError: () => {
            toast.error('Failed to add note');
          },
        }
      );
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Admin Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Manage book requests and approvals
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Pending Requests</p>
          <p className="text-3xl font-bold text-warning mt-1">{pendingRequests.length}</p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Approved Today</p>
          <p className="text-3xl font-bold text-primary mt-1">
            {requests.filter((r) => r.status === 'approved').length}
          </p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Available</p>
          <p className="text-3xl font-bold text-success mt-1">
            {requests.filter((r) => r.status === 'available').length}
          </p>
        </div>
        <div className="p-4 rounded-lg bg-card border border-border">
          <p className="text-sm text-muted-foreground">Total Requests</p>
          <p className="text-3xl font-bold text-foreground mt-1">{requests.length}</p>
        </div>
      </div>

      {/* Pending Requests Table */}
      <div>
        <h2 className="text-lg font-semibold text-foreground mb-4">Pending Approval</h2>
        {pendingRequests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground bg-card rounded-lg border border-border">
            No pending requests
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-secondary/50 hover:bg-secondary/50">
                  <TableHead className="text-muted-foreground">Book</TableHead>
                  <TableHead className="text-muted-foreground">Requested By</TableHead>
                  <TableHead className="text-muted-foreground">Format</TableHead>
                  <TableHead className="text-muted-foreground">Date</TableHead>
                  <TableHead className="text-muted-foreground">Notes</TableHead>
                  <TableHead className="text-right text-muted-foreground">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pendingRequests.map((request) => (
                  <TableRow key={request.id} className="bg-card hover:bg-muted/50">
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <img
                          src={request.book.cover}
                          alt={request.book.title}
                          className="h-12 w-8 rounded object-cover"
                        />
                        <div>
                          <p className="font-medium text-foreground">{request.book.title}</p>
                          <p className="text-sm text-muted-foreground">{request.book.author}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-foreground">{request.userName}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize border-border">
                        {request.format}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(request.createdAt).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-32 truncate">
                      {request.notes || '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setNoteDialog({ open: true, request })}
                        >
                          <MessageSquare className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => handleDeny(request.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          className="bg-success hover:bg-success/90"
                          onClick={() => handleApprove(request.id)}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Note Dialog */}
      <Dialog open={noteDialog.open} onOpenChange={(open) => setNoteDialog({ open, request: null })}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-foreground">Add Admin Note</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Add a note for "{noteDialog.request?.book?.title || 'this request'}"
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label className="text-foreground">Note</Label>
              <Textarea
                value={adminNote}
                onChange={(e) => setAdminNote(e.target.value)}
                placeholder="Enter admin notes..."
                className="bg-secondary border-border"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setNoteDialog({ open: false, request: null })}>
              Cancel
            </Button>
            <Button onClick={handleAddNote}>Save Note</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
