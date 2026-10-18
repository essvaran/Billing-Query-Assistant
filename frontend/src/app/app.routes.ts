import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { adminGuard } from './guards/admin.guard';
import { onboardingGuard } from './guards/onboarding.guard';

export const routes: Routes = [
  // Public
  {
    path: 'login',
    loadComponent: () => import('./components/login/login.component').then(m => m.LoginComponent),
  },

  // Any signed-in user sees the chat only (Docs and Agent modes)
  {
    path: '',
    pathMatch: 'full',
    canActivate: [onboardingGuard],
    loadComponent: () => import('./components/chat/chat.component').then(m => m.ChatComponent),
  },
  { path: 'ask-docs', pathMatch: 'full', redirectTo: '' },

  // Accounts: pick a plan after sign-up, then manage plan, billing profile and invoices
  {
    path: 'onboarding',
    canActivate: [authGuard],
    loadComponent: () => import('./components/onboarding/onboarding.component').then(m => m.OnboardingComponent),
  },
  {
    path: 'account',
    canActivate: [authGuard],
    loadComponent: () => import('./components/account/account.component').then(m => m.AccountComponent),
  },

  // The user guide, filtered to the signed-in role
  {
    path: 'help',
    canActivate: [authGuard],
    loadComponent: () => import('./components/help/help.component').then(m => m.HelpComponent),
  },

  // Operations: admin only (ticket review, escalations, try a ticket)
  {
    path: 'tickets',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/ticket-queue.component').then(m => m.TicketQueueComponent),
  },
  {
    path: 'tickets/:id',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/ticket-workspace.component').then(m => m.TicketWorkspaceComponent),
  },
  {
    path: 'try',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/try-ticket.component').then(m => m.TryTicketComponent),
  },
  {
    path: 'escalations',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/escalations.component').then(m => m.EscalationsComponent),
  },

  // Team lead (admin) routes for the Tier-1 workspace
  {
    path: 'insights',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/insights.component').then(m => m.InsightsComponent),
  },
  {
    path: 'label',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/label-replies.component').then(m => m.LabelRepliesComponent),
  },
  {
    path: 'data',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/data/data.component').then(m => m.DataComponent),
  },
  {
    path: 'trace/:id',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/tier1/trace-view.component').then(m => m.TraceViewComponent),
  },

  // Admin-only routes (dev/research tools)
  {
    path: 'traces',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/traces/traces.component').then(m => m.TracesComponent),
  },
  {
    path: 'sample',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/sample/sample.component').then(m => m.SampleComponent),
  },
  {
    path: 'replay/:traceId',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/replay/replay.component').then(m => m.ReplayComponent),
  },
  {
    path: 'taxonomy',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/taxonomy/taxonomy.component').then(m => m.TaxonomyComponent),
  },
  {
    path: 'eval',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/eval/eval.component').then(m => m.EvalComponent),
  },
  {
    path: 'race',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/race/race.component').then(m => m.RaceComponent),
  },
  {
    path: 'trajectory',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/trajectory/trajectory.component').then(m => m.TrajectoryComponent),
  },
  {
    path: 'admin',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/admin/admin.component').then(m => m.AdminComponent),
  },

  // Shown when a signed-in user opens a team-lead page
  {
    path: 'no-access',
    data: { code: '403', title: 'This page is for the support team',
            desc: 'Your account can use the chat and your account page. If you work on the support team, ask your team lead to give your account the admin role.' },
    loadComponent: () => import('./components/not-found/not-found.component').then(m => m.NotFoundComponent),
  },

  // Fallback
  {
    path: '**',
    loadComponent: () => import('./components/not-found/not-found.component').then(m => m.NotFoundComponent),
  },
];
