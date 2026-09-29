import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService, AppUser, Customer, Order, Ticket } from '../../services/admin.service';
import { UploadService } from '../../services/upload.service';
import { TracesComponent } from '../traces/traces.component';
import { SampleComponent } from '../sample/sample.component';
import { TaxonomyComponent } from '../taxonomy/taxonomy.component';
import { EvalComponent } from '../eval/eval.component';
import { RaceComponent } from '../race/race.component';
import { TrajectoryComponent } from '../trajectory/trajectory.component';

type Tab = 'tickets' | 'orders' | 'customers' | 'users' | 'documents'
         | 'traces' | 'sample' | 'taxonomy' | 'eval' | 'race' | 'trajectory';

interface Toast { message: string; kind: 'success' | 'error'; id: number }

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule,
    TracesComponent, SampleComponent, TaxonomyComponent,
    EvalComponent, RaceComponent, TrajectoryComponent],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  activeTab: Tab = 'tickets';

  tickets: Ticket[] = [];
  orders: Order[] = [];
  customers: Customer[] = [];
  users: AppUser[] = [];

  loading = false;
  saving = false;

  editingTicket: Ticket | null = null;
  editingOrder: Order | null = null;
  editingCustomer: Customer | null = null;

  newTicket: Partial<Ticket> = {};
  newOrder: Partial<Order> = {};
  newCustomer: Partial<Customer> = {};

  showNewTicketForm = false;
  showNewOrderForm = false;
  showNewCustomerForm = false;

  // Inline modal
  confirmModal: { message: string; onConfirm: () => void } | null = null;

  toasts: Toast[] = [];
  private _toastId = 0;

  readonly verdictOptions = ['approve', 'deny', 'escalate'];
  readonly tierOptions = ['standard', 'premium', 'enterprise'];
  readonly statusOptions = ['delivered', 'pending', 'cancelled', 'refunded'];

  uploadState: 'idle' | 'uploading' | 'success' | 'error' = 'idle';
  uploadMessage = '';
  uploadedFileName = '';

  constructor(private svc: AdminService, private uploadSvc: UploadService) {}

  ngOnInit(): void { this.loadAll(); }

  setTab(tab: Tab): void {
    this.activeTab = tab;
    this._clearForms();
  }

  loadAll(): void {
    this._loadTickets();
    this._loadOrders();
    this._loadCustomers();
    this._loadUsers();
  }

  // --------------- Tickets ---------------

  private _loadTickets(): void {
    this.loading = true;
    this.svc.getTickets().subscribe({
      next: data => { this.tickets = data; this.loading = false; },
      error: () => { this._toast('Failed to load tickets', 'error'); this.loading = false; },
    });
  }

  startEditTicket(t: Ticket): void { this.editingTicket = { ...t }; this.showNewTicketForm = false; }
  cancelEditTicket(): void { this.editingTicket = null; }

  saveTicket(): void {
    if (!this.editingTicket) return;
    this.saving = true;
    const { ticket_id, ...rest } = this.editingTicket;
    this.svc.updateTicket(ticket_id, rest).subscribe({
      next: updated => {
        const idx = this.tickets.findIndex(t => t.ticket_id === ticket_id);
        if (idx >= 0) this.tickets[idx] = updated;
        this.editingTicket = null;
        this.saving = false;
        this._toast('Ticket updated', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Update failed', 'error'); this.saving = false; },
    });
  }

  confirmDeleteTicket(id: string): void {
    this.confirmModal = {
      message: `Delete ticket ${id}? This cannot be undone.`,
      onConfirm: () => this._deleteTicket(id),
    };
  }

  private _deleteTicket(id: string): void {
    this.saving = true;
    this.svc.deleteTicket(id).subscribe({
      next: () => {
        this.tickets = this.tickets.filter(t => t.ticket_id !== id);
        this.saving = false;
        this._toast('Ticket deleted', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Delete failed', 'error'); this.saving = false; },
    });
  }

  createTicket(): void {
    const t = this.newTicket;
    if (!t.ticket_id || !t.customer_id || !t.order_id || !t.text) {
      this._toast('All required fields must be filled', 'error'); return;
    }
    this.saving = true;
    this.svc.createTicket(t as Ticket).subscribe({
      next: created => {
        this.tickets = [...this.tickets, created].sort((a, b) => a.ticket_id.localeCompare(b.ticket_id));
        this.newTicket = {};
        this.showNewTicketForm = false;
        this.saving = false;
        this._toast('Ticket created', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Create failed', 'error'); this.saving = false; },
    });
  }

  // --------------- Orders ---------------

  private _loadOrders(): void {
    this.svc.getOrders().subscribe({
      next: data => (this.orders = data),
      error: () => this._toast('Failed to load orders', 'error'),
    });
  }

  startEditOrder(o: Order): void { this.editingOrder = { ...o }; this.showNewOrderForm = false; }
  cancelEditOrder(): void { this.editingOrder = null; }

  saveOrder(): void {
    if (!this.editingOrder) return;
    this.saving = true;
    const { order_id, ...rest } = this.editingOrder;
    this.svc.updateOrder(order_id, { ...rest, amount_usd: +rest.amount_usd }).subscribe({
      next: updated => {
        const idx = this.orders.findIndex(o => o.order_id === order_id);
        if (idx >= 0) this.orders[idx] = updated;
        this.editingOrder = null;
        this.saving = false;
        this._toast('Order updated', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Update failed', 'error'); this.saving = false; },
    });
  }

  confirmDeleteOrder(id: string): void {
    this.confirmModal = {
      message: `Delete order ${id}? This cannot be undone.`,
      onConfirm: () => this._deleteOrder(id),
    };
  }

  private _deleteOrder(id: string): void {
    this.saving = true;
    this.svc.deleteOrder(id).subscribe({
      next: () => {
        this.orders = this.orders.filter(o => o.order_id !== id);
        this.saving = false;
        this._toast('Order deleted', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Delete failed', 'error'); this.saving = false; },
    });
  }

  createOrder(): void {
    const o = this.newOrder;
    if (!o.order_id || !o.purchase_date || o.amount_usd == null || !o.status) {
      this._toast('All required fields must be filled', 'error'); return;
    }
    this.saving = true;
    this.svc.createOrder({ ...o, amount_usd: +o.amount_usd! } as Order).subscribe({
      next: created => {
        this.orders = [...this.orders, created].sort((a, b) => a.order_id.localeCompare(b.order_id));
        this.newOrder = {};
        this.showNewOrderForm = false;
        this.saving = false;
        this._toast('Order created', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Create failed', 'error'); this.saving = false; },
    });
  }

  // --------------- Customers ---------------

  private _loadCustomers(): void {
    this.svc.getCustomers().subscribe({
      next: data => (this.customers = data),
      error: () => this._toast('Failed to load customers', 'error'),
    });
  }

  startEditCustomer(c: Customer): void { this.editingCustomer = { ...c }; this.showNewCustomerForm = false; }
  cancelEditCustomer(): void { this.editingCustomer = null; }

  saveCustomer(): void {
    if (!this.editingCustomer) return;
    this.saving = true;
    const { customer_id, ...rest } = this.editingCustomer;
    this.svc.updateCustomer(customer_id, { ...rest, refund_days: +rest.refund_days }).subscribe({
      next: updated => {
        const idx = this.customers.findIndex(c => c.customer_id === customer_id);
        if (idx >= 0) this.customers[idx] = updated;
        this.editingCustomer = null;
        this.saving = false;
        this._toast('Customer updated', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Update failed', 'error'); this.saving = false; },
    });
  }

  confirmDeleteCustomer(id: string): void {
    this.confirmModal = {
      message: `Delete customer ${id}? This cannot be undone.`,
      onConfirm: () => this._deleteCustomer(id),
    };
  }

  private _deleteCustomer(id: string): void {
    this.saving = true;
    this.svc.deleteCustomer(id).subscribe({
      next: () => {
        this.customers = this.customers.filter(c => c.customer_id !== id);
        this.saving = false;
        this._toast('Customer deleted', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Delete failed', 'error'); this.saving = false; },
    });
  }

  createCustomer(): void {
    const c = this.newCustomer;
    if (!c.customer_id || !c.tier || c.refund_days == null) {
      this._toast('All required fields must be filled', 'error'); return;
    }
    this.saving = true;
    this.svc.createCustomer({ ...c, refund_days: +c.refund_days! } as Customer).subscribe({
      next: created => {
        this.customers = [...this.customers, created].sort((a, b) => a.customer_id.localeCompare(b.customer_id));
        this.newCustomer = {};
        this.showNewCustomerForm = false;
        this.saving = false;
        this._toast('Customer created', 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Create failed', 'error'); this.saving = false; },
    });
  }

  // --------------- Users ---------------

  private _loadUsers(): void {
    this.svc.getUsers().subscribe({
      next: data => (this.users = data),
      error: () => this._toast('Failed to load users', 'error'),
    });
  }

  setUserRole(user: AppUser, role: 'admin' | 'user'): void {
    if (user.role === role) return;
    this.saving = true;
    this.svc.updateUserRole(user.id, role).subscribe({
      next: updated => {
        const idx = this.users.findIndex(u => u.id === updated.id);
        if (idx >= 0) this.users[idx] = updated;
        this.saving = false;
        this._toast(`${updated.email} is now ${updated.role}`, 'success');
      },
      error: err => { this._toast(err?.error?.detail ?? 'Role update failed', 'error'); this.saving = false; },
    });
  }

  // --------------- Upload ---------------

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    const file = input.files[0];
    input.value = '';

    this.uploadState = 'uploading';
    this.uploadedFileName = file.name;
    this.uploadMessage = '';

    this.uploadSvc.uploadDocument(file).subscribe({
      next: (res) => {
        this.uploadState = 'success';
        this.uploadMessage = `Indexed ${res.chunks_indexed} chunks from "${res.filename}"`;
      },
      error: (err) => {
        this.uploadState = 'error';
        this.uploadMessage = err?.error?.detail ?? 'Upload failed';
      },
    });
  }

  resetUpload(): void {
    this.uploadState = 'idle';
    this.uploadMessage = '';
    this.uploadedFileName = '';
  }

  // --------------- Modal ---------------

  dismissModal(): void { this.confirmModal = null; }

  executeModal(): void {
    if (!this.confirmModal) return;
    this.confirmModal.onConfirm();
    this.confirmModal = null;
  }

  // --------------- Toast ---------------

  private _toast(message: string, kind: 'success' | 'error'): void {
    const id = ++this._toastId;
    this.toasts.push({ message, kind, id });
    setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 3500);
  }

  dismissToast(id: number): void { this.toasts = this.toasts.filter(t => t.id !== id); }

  // --------------- Helpers ---------------

  private _clearForms(): void {
    this.editingTicket = null;
    this.editingOrder = null;
    this.editingCustomer = null;
    this.showNewTicketForm = false;
    this.showNewOrderForm = false;
    this.showNewCustomerForm = false;
    this.newTicket = {};
    this.newOrder = {};
    this.newCustomer = {};
  }
}
