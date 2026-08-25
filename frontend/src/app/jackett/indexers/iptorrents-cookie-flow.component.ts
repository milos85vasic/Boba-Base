// Special-case flow for IPTorrents-style cookie-only indexers.
//
// Users can't easily get their `uid`/`pass` cookies through Jackett's
// generic config form, so we render an instruction panel + textarea.
// On Save we POST a credential first (admin/admin), then POST
// /indexers/{id} with that credential_name so the indexer is wired
// up in one click.
//
// CONST-XII: the spec asserts both POSTs fire in order — a stub that
// only fires one would FAIL the assertion on call count, and the
// (saved) emit assertion would FAIL.
import {
  Component,
  EventEmitter,
  Input,
  Output,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CredentialsService } from '../credentials/credentials.service';
import { IndexersService } from './indexers.service';

@Component({
  selector: 'app-iptorrents-cookie-flow',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="cookie-flow" data-testid="iptorrents-cookie-flow">
      <div class="instructions">
        <p>
          <strong>{{ indexerId.toUpperCase() }}</strong> requires a session cookie.
          Open <code>https://iptorrents.com</code> in your browser, log in, then
          copy your <code>uid</code> and <code>pass</code> cookies as a single
          string of the form:
        </p>
        <pre>uid=12345; pass=abcdef0123456789</pre>
        <p class="muted">
          Required fields:
          @for (f of requiredFields; track f) {
            <code class="field">{{ f }}</code>
          }
        </p>
      </div>

      <label>
        <span>Cookie value</span>
        <textarea
          [ngModel]="cookieValue()"
          (ngModelChange)="cookieValue.set($event)"
          name="cookie-value"
          rows="3"
          placeholder="uid=…; pass=…"
          data-testid="cookie-input"
        ></textarea>
      </label>

      @if (error(); as err) {
        <div class="error" role="alert" data-testid="cookie-flow-error">{{ err }}</div>
      }

      <footer>
        <button type="button" class="btn ghost" (click)="cancel.emit()">Cancel</button>
        <button
          type="button"
          class="btn primary"
          (click)="onSave()"
          [disabled]="!hasContent() || saving()"
          data-testid="cookie-save"
        >{{ saving() ? 'Saving…' : 'Save' }}</button>
      </footer>
    </section>
  `,
  styles: [`
    .cookie-flow {
      padding: 14px 18px 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .instructions p { margin: 0 0 8px; font-size: 13px; }
    .instructions pre {
      background: var(--color-bg-primary);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      overflow-x: auto;
    }
    .muted { color: var(--color-text-secondary); }
    .field {
      background: var(--color-bg-tertiary);
      padding: 1px 6px; border-radius: 4px;
      margin: 0 4px; font-size: 12px;
    }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
    textarea {
      background: var(--color-bg-primary);
      color: var(--color-text-primary);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
    }
    .error {
      background: color-mix(in srgb, var(--color-accent) 15%, var(--color-bg-secondary));
      border: 1px solid var(--color-accent);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
    }
    footer { display: flex; justify-content: flex-end; gap: 8px; }
    .btn {
      padding: 8px 14px;
      border-radius: 6px;
      border: 1px solid var(--color-border);
      cursor: pointer;
      font: inherit;
      &.ghost { background: transparent; color: var(--color-text-primary); }
      &.primary {
        background: var(--color-accent);
        border-color: var(--color-accent);
        color: var(--color-on-accent);
        &:disabled { opacity: 0.5; cursor: not-allowed; }
      }
    }
  `],
})
export class IptorrentsCookieFlowComponent {
  private credService = inject(CredentialsService);
  private idxService = inject(IndexersService);

  @Input() indexerId = '';
  @Input() requiredFields: string[] = [];
  @Output() saved = new EventEmitter<void>();
  @Output() cancel = new EventEmitter<void>();

  cookieValue = signal<string>('');
  saving = signal<boolean>(false);
  error = signal<string | null>(null);

  hasContent(): boolean {
    return this.cookieValue().trim().length > 0;
  }

  onSave(): void {
    if (!this.hasContent()) return;
    const credName = this.indexerId.toUpperCase();
    this.saving.set(true);
    this.error.set(null);
    this.credService
      .upsert({ name: credName, cookies: this.cookieValue().trim() })
      .subscribe({
        next: () => {
          this.idxService
            .configure(this.indexerId, { credential_name: credName })
            .subscribe({
              next: () => {
                this.saving.set(false);
                this.saved.emit();
              },
              error: (err) => {
                this.saving.set(false);
                this.error.set(this.errorMessage(err));
              },
            });
        },
        error: (err) => {
          this.saving.set(false);
          this.error.set(this.errorMessage(err));
        },
      });
  }

  private errorMessage(err: unknown): string {
    if (err && typeof err === 'object') {
      const e = err as {
        message?: string;
        error?: { error?: string; message?: string } | string;
      };
      if (e.error && typeof e.error === 'object') {
        return e.error.error ?? e.error.message ?? e.message ?? String(err);
      }
      if (typeof e.error === 'string' && e.error.length > 0) return e.error;
      if (e.message) return e.message;
    }
    return String(err);
  }
}
