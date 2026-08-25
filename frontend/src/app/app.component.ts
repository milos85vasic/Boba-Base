// Application shell. Mounts:
//   • a top-level nav (Dashboard, Jackett)
//   • <router-outlet> for feature pages
//   • global toast / confirm-dialog / footer chrome
//
// Pre-Phase-5 the shell rendered <app-dashboard> directly. Phase 5
// introduces the lazy-loaded `/jackett` route tree, so the dashboard
// is now mounted as the `path: ''` route via the router (see
// app.routes.ts) and the shell is router-driven.
import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ToastContainerComponent } from './components/toast-container/toast-container.component';
import { ConfirmDialogComponent } from './components/confirm-dialog/confirm-dialog.component';
import { SiteFooterComponent } from './components/site-footer/site-footer.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ToastContainerComponent,
    ConfirmDialogComponent,
    SiteFooterComponent,
  ],
  template: `
    <nav class="app-nav" aria-label="Primary">
      <div class="brand">{{ title }}</div>
      <ul class="nav-links">
        <li>
          <a
            routerLink="/"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            data-testid="nav-dashboard"
          >Dashboard</a>
        </li>
        <li>
          <a
            routerLink="/jackett"
            routerLinkActive="active"
            data-testid="nav-jackett"
          >Jackett</a>
        </li>
      </ul>
    </nav>
    <main class="app-main">
      <router-outlet />
    </main>
    <app-toast-container></app-toast-container>
    <app-confirm-dialog></app-confirm-dialog>
    <app-site-footer></app-site-footer>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      background: var(--color-bg-primary);
      color: var(--color-text-primary);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    }
    .app-nav {
      display: flex;
      align-items: center;
      gap: 24px;
      padding: 10px 24px;
      background: var(--color-bg-secondary);
      border-bottom: 1px solid var(--color-border);
      box-shadow: var(--shadow-elev-1);
    }
    .brand {
      font-weight: 700;
      color: var(--color-accent-text);
      letter-spacing: 0.02em;
      text-shadow: var(--shadow-text-md);
    }
    .nav-links {
      display: flex;
      gap: 4px;
      list-style: none;
      padding: 0;
      margin: 0;
    }
    .nav-links a {
      display: inline-block;
      padding: 6px 14px;
      border-radius: 6px;
      text-decoration: none;
      color: var(--color-text-primary);
      font-size: 14px;
      transition: background 0.15s ease, color 0.15s ease;
    }
    .nav-links a:hover { background: var(--color-bg-tertiary); }
    .nav-links a.active {
      background: var(--color-accent);
      color: var(--color-on-accent);
      box-shadow: var(--shadow-elev-1);
    }
    .app-main {
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
    }
  `],
})
export class AppComponent {
  title = 'Боба Dashboard';
}
