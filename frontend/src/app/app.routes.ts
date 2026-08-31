import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat.component';
import { TracesComponent } from './components/traces/traces.component';
import { SampleComponent } from './components/sample/sample.component';
import { ReplayComponent } from './components/replay/replay.component';
import { TaxonomyComponent } from './components/taxonomy/taxonomy.component';

export const routes: Routes = [
  { path: '', component: ChatComponent },
  { path: 'traces', component: TracesComponent },
  { path: 'sample', component: SampleComponent },
  { path: 'replay/:traceId', component: ReplayComponent },
  { path: 'taxonomy', component: TaxonomyComponent },
];
