// Inline modal-style dialog for creating/editing a single credential.
//
// Self-review: this is NOT a CDK overlay — it's a fixed-position
// `<div>` rendered conditionally by the parent via `@if (showDialog())`.
// CDK overlay can be retrofitted later (Task 28+) without changing the
// public API of this component (Inputs/Outputs).
//
// PATCH semantics: when editing, we DO NOT prefill plaintext (the API
// never returns it). Inputs start blank with placeholder hints; only
// fields the operator actually types are sent on the upsert body. The
// `name` input is read-only when editing because it's the primary key.
import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CredentialMetadata, CredentialUpsertBody } from './credentials.service';

@Component({
  selector: 'app-credential-edit-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="dialog-backdrop" data-testid="edit-dialog">
      <div class="dialog">
        <header>
          <h3>{{ existing ? 'Edit credential' : 'Add credential' }}</h3>
          <button type="button" class="close" (click)="cancel.emit()" aria-label="Close">×</button>
        </header>
        <form (submit)="$event.preventDefault(); onSubmit()">
          <label>
            <span>Name</span>
            <input
              type="text"
              [ngModel]="name()"
              (ngModelChange)="name.set($event.toUpperCase())"
              [readonly]="!!existing"
              name="name"
              placeholder="RUTRACKER"
              data-testid="input-name"
              required
            />
          </label>
          <label>
            <span>Username</span>
            <input
              type="text"
              [ngModel]="username()"
              (ngModelChange)="username.set($event)"
              name="username"
              [placeholder]="existing?.has_username ? '(leave blank to keep current)' : 'username'"
              data-testid="input-username"
              autocomplete="off"
            />
          </label>
          <label>
            <span>Password</span>
            <input
              type="password"
              [ngModel]="password()"
              (ngModelChange)="password.set($event)"
              name="password"
              [placeholder]="existing?.has_password ? '(leave blank to keep current)' : 'password'"
              data-testid="input-password"
              autocomplete="off"
            />
          </label>
          <label>
            <span>Cookies</span>
            <textarea
              [ngModel]="cookies()"
              (ngModelChange)="cookies.set($event)"
              name="cookies"
              [placeholder]="existing?.has_cookies ? '(leave blank to keep current)' : 'cookies'"
              data-testid="input-cookies"
              rows="3"
            ></textarea>
          </label>
          <footer>
            <button type="button" class="btn ghost" (click)="cancel.emit()">Cancel</button>
            <button type="submit" class="btn primary" data-testid="save-credential">Save</button>
          </footer>
        </form>
      </div>
    </div>
  `,
  styles: [`
    .dialog-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.55);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .dialog {
      background: var(--color-bg-secondary);
      color: var(--color-text-primary);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      box-shadow: var(--shadow-elev-3);
      width: min(440px, 92vw);
      padding: 0;
      overflow: hidden;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--color-border);
      h3 { margin: 0; font-size: 16px; color: var(--color-accent-text); text-shadow: var(--shadow-text-md); }
      .close {
        background: transparent; border: 0; color: var(--color-text-secondary);
        font-size: 22px; line-height: 1; cursor: pointer;
        &:hover { color: var(--color-text-primary); }
      }
    }
    form { padding: 14px 18px 18px; display: flex; flex-direction: column; gap: 12px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
    input, textarea {
      background: var(--color-bg-primary);
      color: var(--color-text-primary);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      &:focus { outline: 2px solid var(--color-accent); outline-offset: 0; }
      &[readonly] { opacity: 0.6; cursor: not-allowed; }
    }
    footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
    .btn {
      padding: 8px 14px;
      border-radius: 6px;
      border: 1px solid var(--color-border);
      cursor: pointer;
      font: inherit;
      &.ghost { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
      &.primary {
        background: var(--color-accent);
        border-color: var(--color-accent);
        color: var(--color-on-accent);
        box-shadow: var(--shadow-elev-2);
        &:hover { background: var(--color-accent-hover); color: var(--color-on-accent-hover); }
      }
    }
  `],
})
export class CredentialEditDialogComponent {
  /** When set, dialog is in EDIT mode (name read-only, placeholders show "leave blank to keep"). */
  @Input() existing: CredentialMetadata | null = null;

  @Output() save = new EventEmitter<CredentialUpsertBody>();
  @Output() cancel = new EventEmitter<void>();

  name = signal('');
  username = signal('');
  password = signal('');
  cookies = signal('');

  ngOnChanges(): void {
    // When opened in edit mode, prefill the name (only) — plaintext
    // values are never echoed by the API and stay blank.
    if (this.existing) {
      this.name.set(this.existing.name);
    } else {
      this.name.set('');
    }
    this.username.set('');
    this.password.set('');
    this.cookies.set('');
  }

  onSubmit(): void {
    const body: CredentialUpsertBody = { name: this.name().trim() };
    const u = this.username();
    const p = this.password();
    const c = this.cookies();
    if (u !== '') body.username = u;
    if (p !== '') body.password = p;
    if (c !== '') body.cookies = c;
    if (!body.name) return; // name is required
    this.save.emit(body);
  }
}
