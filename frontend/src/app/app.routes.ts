import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { adminGuard } from './guards/admin.guard';

export const routes: Routes = [
  // Public
  {
    path: 'login',
    loadComponent: () => import('./components/login/login.component').then(m => m.LoginComponent),
  },

  // Authenticated — lazy-loaded for smaller initial bundle
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./components/chat/chat.component').then(m => m.ChatComponent),
  },
  {
    path: 'traces',
    canActivate: [authGuard],
    loadComponent: () => import('./components/traces/traces.component').then(m => m.TracesComponent),
  },
  {
    path: 'sample',
    canActivate: [authGuard],
    loadComponent: () => import('./components/sample/sample.component').then(m => m.SampleComponent),
  },
  {
    path: 'replay/:traceId',
    canActivate: [authGuard],
    loadComponent: () => import('./components/replay/replay.component').then(m => m.ReplayComponent),
  },
  {
    path: 'taxonomy',
    canActivate: [authGuard],
    loadComponent: () => import('./components/taxonomy/taxonomy.component').then(m => m.TaxonomyComponent),
  },
  {
    path: 'eval',
    canActivate: [authGuard],
    loadComponent: () => import('./components/eval/eval.component').then(m => m.EvalComponent),
  },
  {
    path: 'race',
    canActivate: [authGuard],
    loadComponent: () => import('./components/race/race.component').then(m => m.RaceComponent),
  },
  {
    path: 'trajectory',
    canActivate: [authGuard],
    loadComponent: () => import('./components/trajectory/trajectory.component').then(m => m.TrajectoryComponent),
  },
  {
    path: 'agent-chat',
    canActivate: [authGuard],
    loadComponent: () => import('./components/agent-chat/agent-chat.component').then(m => m.AgentChatComponent),
  },

  // Admin only
  {
    path: 'admin',
    canActivate: [adminGuard],
    loadComponent: () => import('./components/admin/admin.component').then(m => m.AdminComponent),
  },

  // Fallback
  {
    path: '**',
    loadComponent: () => import('./components/not-found/not-found.component').then(m => m.NotFoundComponent),
  },
];
