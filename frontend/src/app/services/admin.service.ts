import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Ticket {
  ticket_id: string;
  customer_id: string;
  order_id: string;
  text: string;
  expected_verdict: string | null;
}

export interface Order {
  order_id: string;
  purchase_date: string;
  amount_usd: number;
  status: string;
}

export interface Customer {
  customer_id: string;
  tier: string;
  refund_days: number;
}

export interface AppUser {
  id: number;
  email: string;
  role: 'admin' | 'user';
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  constructor(private http: HttpClient) {}

  // ---- Tickets ----
  getTickets(offset = 0, limit = 50): Observable<Ticket[]> {
    const params = new HttpParams().set('offset', offset).set('limit', limit);
    return this.http.get<Ticket[]>('/api/admin/tickets', { params });
  }
  createTicket(body: Omit<Ticket, never>): Observable<Ticket> {
    return this.http.post<Ticket>('/api/admin/tickets', body);
  }
  updateTicket(id: string, body: Partial<Ticket>): Observable<Ticket> {
    return this.http.put<Ticket>(`/api/admin/tickets/${id}`, body);
  }
  deleteTicket(id: string): Observable<void> {
    return this.http.delete<void>(`/api/admin/tickets/${id}`);
  }

  // ---- Orders ----
  getOrders(offset = 0, limit = 50): Observable<Order[]> {
    const params = new HttpParams().set('offset', offset).set('limit', limit);
    return this.http.get<Order[]>('/api/admin/orders', { params });
  }
  createOrder(body: Order): Observable<Order> {
    return this.http.post<Order>('/api/admin/orders', body);
  }
  updateOrder(id: string, body: Partial<Order>): Observable<Order> {
    return this.http.put<Order>(`/api/admin/orders/${id}`, body);
  }
  deleteOrder(id: string): Observable<void> {
    return this.http.delete<void>(`/api/admin/orders/${id}`);
  }

  // ---- Customers ----
  getCustomers(offset = 0, limit = 50): Observable<Customer[]> {
    const params = new HttpParams().set('offset', offset).set('limit', limit);
    return this.http.get<Customer[]>('/api/admin/customers', { params });
  }
  createCustomer(body: Customer): Observable<Customer> {
    return this.http.post<Customer>('/api/admin/customers', body);
  }
  updateCustomer(id: string, body: Partial<Customer>): Observable<Customer> {
    return this.http.put<Customer>(`/api/admin/customers/${id}`, body);
  }
  deleteCustomer(id: string): Observable<void> {
    return this.http.delete<void>(`/api/admin/customers/${id}`);
  }

  // ---- Users ----
  getUsers(offset = 0, limit = 100): Observable<AppUser[]> {
    const params = new HttpParams().set('offset', offset).set('limit', limit);
    return this.http.get<AppUser[]>('/api/admin/users', { params });
  }
  updateUserRole(id: number, role: 'admin' | 'user'): Observable<AppUser> {
    return this.http.put<AppUser>(`/api/admin/users/${id}/role`, { role });
  }
}
