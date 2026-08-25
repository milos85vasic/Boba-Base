import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-qbit-login-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    @if (visible()) {
      <div class="modal-overlay show" (click)="onBackdrop($event)">
        <div class="modal">
          <h3>Login to qBittorrent</h3>
          <p class="hint">Enter your qBittorrent WebUI credentials.</p>
          <input type="text" [(ngModel)]="username" placeholder="Username" />
          <input type="password" [(ngModel)]="password" placeholder="Password" />
          <label class="save-label">
            <input type="checkbox" [(ngModel)]="saveCreds" /> Remember me
          </label>
          <div class="error" *ngIf="error()">{{ error() }}</div>
          <div class="modal-actions">
            <button class="cancel-btn" (click)="close()">Cancel</button>
            <button class="submit-btn" [disabled]="loading()" (click)="login()">
              {{ loading() ? 'Logging in...' : 'Login' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 10001; justify-content: center; align-items: center; }
    .modal-overlay.show { display: flex; }
    .modal { background: var(--color-bg-secondary); padding: 28px; border-radius: 12px; border: 1px solid var(--color-border); max-width: 400px; width: 90%; color: var(--color-text-primary); box-shadow: var(--shadow-elev-3); }
    .modal h3 { color: var(--color-accent-text); margin-bottom: 6px; font-size: 20px; text-shadow: var(--shadow-text-md); }
    .hint { color: var(--color-text-secondary); font-size: 13px; margin-bottom: 16px; }
    input[type="text"], input[type="password"] { width: 100%; padding: 12px; margin-bottom: 12px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-bg-primary); color: var(--color-text-primary); font-size: 15px; }
    .save-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--color-text-secondary); margin-bottom: 14px; }
    .save-label input { width: auto; }
    .error { color: var(--color-danger-text); font-size: 13px; margin-bottom: 12px; text-shadow: var(--shadow-text-xs); }
    .modal-actions { display: flex; gap: 10px; }
    .modal-actions button { flex: 1; padding: 10px; border-radius: 8px; border: none; cursor: pointer; font-size: 15px; box-shadow: var(--shadow-elev-1); transition: box-shadow 0.12s ease, transform 0.08s ease; }
    .modal-actions button:hover { box-shadow: var(--shadow-elev-2); transform: translateY(-1px); }
    .modal-actions button:active { transform: translateY(0); box-shadow: var(--shadow-elev-1); }
    .cancel-btn { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
    .submit-btn { background: var(--color-accent); color: var(--color-on-accent); }
    .submit-btn:disabled { background: var(--color-text-secondary); cursor: not-allowed; box-shadow: none; transform: none; }
  `]
})
export class QbitLoginDialogComponent {
  private api = inject(ApiService);
  private toast = inject(ToastService);

  visible = signal(false);
  username = signal('admin');
  password = signal('');
  saveCreds = signal(false);
  loading = signal(false);
  error = signal('');
  onSuccess?: () => void;

  open(onSuccess?: () => void): void {
    this.visible.set(true);
    this.error.set('');
    this.onSuccess = onSuccess;
  }

  close(): void {
    this.visible.set(false);
  }

  login(): void {
    if (!this.username() || !this.password()) {
      this.error.set('Please enter username and password');
      return;
    }
    this.loading.set(true);
    this.api.qbitLogin({
      username: this.username(),
      password: this.password(),
      save: this.saveCreds()
    }).subscribe({
      next: (res) => {
        this.loading.set(false);
        if (res.status === 'authenticated') {
          this.toast.success('Logged in to qBittorrent');
          this.close();
          this.onSuccess?.();
        } else {
          this.error.set(res.error || 'Login failed');
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err.error?.error || 'Connection error');
      }
    });
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.close();
  }
}
