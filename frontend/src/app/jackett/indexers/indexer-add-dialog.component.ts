// Inline modal dialog for "Add this catalog indexer to my install".
//
// Operator picks an existing credential by name (or, in cookie-only
// flows, the IPTorrents flow component handles the special path
// upstream). The dialog displays the indexer's `required_fields` so
// the operator can see what kind of credential to pick.
//
// Spec ties this to two upstream services:
//   - CredentialsService.list  → populate the credential dropdown.
//   - IndexersService.configure → POST /indexers/{id} on Save.
import {
  Component,
  EventEmitter,
  Input,
  OnInit,
  Output,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CredentialsService,
  CredentialMetadata,
} from '../credentials/credentials.service';
import {
  IndexersService,
  CatalogItem,
} from './indexers.service';
import { IptorrentsCookieFlowComponent } from './iptorrents-cookie-flow.component';

@Component({
  selector: 'app-indexer-add-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IptorrentsCookieFlowComponent],
  template: `
    <div class="dialog-backdrop" data-testid="indexer-add-dialog">
      <div class="dialog">
        <header>
          <h3>Add indexer: {{ item?.display_name }}</h3>
          <button type="button" class="close" (click)="cancel.emit()" aria-label="Close">×</button>
        </header>

        @if (isCookieOnly()) {
          <app-iptorrents-cookie-flow
            [indexerId]="item!.id"
            [requiredFields]="item!.required_fields"
            (saved)="onCookieFlowSaved()"
            (cancel)="cancel.emit()"
          ></app-iptorrents-cookie-flow>
        } @else {
          <form (submit)="$event.preventDefault(); onSubmit()">
            <p class="hint">
              Required fields:
              @for (f of item?.required_fields; track f) {
                <code class="field">{{ f }}</code>
              }
            </p>

            <label>
              <span>Credential</span>
              <select
                [ngModel]="credentialName()"
                (ngModelChange)="credentialName.set($event)"
                name="credential_name"
                data-testid="credential-select"
                required
              >
                <option value="" disabled>Select…</option>
                @for (c of credentials(); track c.name) {
                  <option [value]="c.name">{{ c.name }} ({{ c.kind }})</option>
                }
              </select>
            </label>

            @if (error(); as err) {
              <div class="error" role="alert" data-testid="dialog-error">{{ err }}</div>
            }

            <footer>
              <button type="button" class="btn ghost" (click)="cancel.emit()">Cancel</button>
              <button
                type="submit"
                class="btn primary"
                data-testid="save-indexer"
                [disabled]="!credentialName()"
              >Save</button>
            </footer>
          </form>
        }
      </div>
    </div>
  `,
  styles: [`
    .dialog-backdrop {
      position: fixed; inset: 0;
      background: rgba(0, 0, 0, 0.55);
      display: flex; align-items: center; justify-content: center;
      z-index: 1000;
    }
    .dialog {
      background: var(--color-bg-secondary);
      color: var(--color-text-primary);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      box-shadow: var(--shadow-elev-3);
      width: min(520px, 92vw);
      overflow: hidden;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--color-border);
      h3 { margin: 0; font-size: 16px; color: var(--color-accent-text); }
      .close {
        background: transparent; border: 0;
        color: var(--color-text-secondary);
        font-size: 22px; cursor: pointer;
        &:hover { color: var(--color-text-primary); }
      }
    }
    form { padding: 14px 18px 18px; display: flex; flex-direction: column; gap: 12px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
    select {
      background: var(--color-bg-primary);
      color: var(--color-text-primary);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
    }
    .hint {
      margin: 0;
      color: var(--color-text-secondary);
      font-size: 13px;
      .field {
        background: var(--color-bg-tertiary);
        padding: 1px 6px; border-radius: 4px;
        margin: 0 4px; font-size: 12px;
      }
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
export class IndexerAddDialogComponent implements OnInit {
  private credService = inject(CredentialsService);
  private idxService = inject(IndexersService);

  @Input() item: CatalogItem | null = null;
  @Output() saved = new EventEmitter<void>();
  @Output() cancel = new EventEmitter<void>();

  credentials = signal<CredentialMetadata[]>([]);
  credentialName = signal<string>('');
  error = signal<string | null>(null);

  ngOnInit(): void {
    this.credService.list().subscribe({
      next: (rows) => this.credentials.set(rows ?? []),
      error: (err) => this.error.set(this.errorMessage(err)),
    });
  }

  /** Cookie-only indexers (e.g. IPTorrents) need the special flow. */
  isCookieOnly(): boolean {
    if (!this.item) return false;
    const fs = (this.item.required_fields ?? []).map((f) => f.toLowerCase());
    const hasCookie = fs.some((f) => f.includes('cookie'));
    const hasUserPass =
      fs.some((f) => f === 'username' || f === 'user') &&
      fs.some((f) => f === 'password' || f === 'pass');
    return hasCookie && !hasUserPass;
  }

  onCookieFlowSaved(): void {
    this.saved.emit();
  }

  onSubmit(): void {
    if (!this.item || !this.credentialName()) return;
    this.idxService
      .configure(this.item.id, { credential_name: this.credentialName() })
      .subscribe({
        next: () => this.saved.emit(),
        error: (err) => this.error.set(this.errorMessage(err)),
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
