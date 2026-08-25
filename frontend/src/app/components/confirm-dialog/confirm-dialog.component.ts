import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DialogService } from '../../services/dialog.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (dialogService.confirmDialog().visible) {
      <div class="modal-overlay show" (click)="onBackdrop($event)">
        <div class="modal">
          <h3>{{ dialogService.confirmDialog().data.title }}</h3>
          <p class="modal-message">{{ dialogService.confirmDialog().data.message }}</p>
          <div class="modal-actions">
            <button class="cancel-btn" (click)="dialogService.resolveConfirm(false)">
              {{ dialogService.confirmDialog().data.cancelText || 'Cancel' }}
            </button>
            <button
              class="submit-btn"
              [class.btn-danger]="dialogService.confirmDialog().data.confirmClass === 'danger'"
              (click)="dialogService.resolveConfirm(true)">
              {{ dialogService.confirmDialog().data.confirmText || 'Confirm' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    .modal-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.6);
      z-index: 10000;
      justify-content: center;
      align-items: center;
    }
    .modal-overlay.show { display: flex; }
    .modal {
      background: var(--color-bg-secondary);
      padding: 28px;
      border-radius: 12px;
      border: 1px solid var(--color-border);
      max-width: 420px;
      width: 90%;
      color: var(--color-text-primary);
      box-shadow: var(--shadow-elev-3);
    }
    .modal h3 {
      color: var(--color-accent-text);
      margin-bottom: 14px;
      font-size: 20px;
      text-shadow: var(--shadow-text-md);
    }
    .modal-message {
      font-size: 15px;
      margin-bottom: 22px;
      line-height: 1.5;
    }
    .modal-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .modal-actions button {
      flex: 1;
      min-width: 100px;
      padding: 10px 16px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      font-size: 15px;
      font-weight: 500;
      box-shadow: var(--shadow-elev-1);
      transition: box-shadow 0.12s ease, transform 0.08s ease, background 0.12s ease;
    }
    .modal-actions button:hover { box-shadow: var(--shadow-elev-2); transform: translateY(-1px); }
    .modal-actions button:active { transform: translateY(0); box-shadow: var(--shadow-elev-1); }
    .cancel-btn { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
    .cancel-btn:hover { background: var(--color-border); color: var(--color-on-border); }
    .submit-btn { background: var(--color-accent); color: var(--color-on-accent); }
    .submit-btn:hover { background: var(--color-accent-hover); color: var(--color-on-accent-hover); }
    .btn-danger { background: var(--color-danger) !important; color: var(--color-on-danger) !important; }
  `]
})
export class ConfirmDialogComponent {
  dialogService = inject(DialogService);

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.dialogService.resolveConfirm(false);
    }
  }
}
