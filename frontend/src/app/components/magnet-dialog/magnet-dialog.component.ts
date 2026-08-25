import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-magnet-dialog',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (visible()) {
      <div class="modal-overlay show" (click)="onBackdrop($event)">
        <div class="modal">
          <h3>Magnet Link</h3>
          <p class="hint">Share or open this magnet link in your torrent client.</p>
          <textarea readonly onclick="this.select()">{{ magnet() }}</textarea>
          <div class="modal-actions">
            <button class="cancel-btn" (click)="close()">Close</button>
            <button class="submit-btn" (click)="copy()">Copy</button>
            <a class="submit-btn btn-open" [href]="magnet()"
               (click)="closeAfterOpen()">Open</a>
            <button class="submit-btn btn-add" (click)="onAdd()">Add</button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 10001; justify-content: center; align-items: center; }
    .modal-overlay.show { display: flex; }
    .modal { background: var(--color-bg-secondary); padding: 28px; border-radius: 12px; border: 1px solid var(--color-border); max-width: 480px; width: 90%; color: var(--color-text-primary); box-shadow: var(--shadow-elev-3); }
    .modal h3 { color: var(--color-accent-text); margin-bottom: 6px; font-size: 20px; text-shadow: var(--shadow-text-md); }
    .hint { color: var(--color-text-secondary); font-size: 13px; margin-bottom: 16px; }
    textarea { width: 100%; height: 80px; padding: 10px; background: var(--color-bg-primary); border: 1px solid var(--color-border); color: var(--color-text-primary); font-family: monospace; font-size: 12px; border-radius: 6px; resize: none; margin-bottom: 16px; }
    .modal-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .modal-actions > * { flex: 1; min-width: 80px; padding: 10px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px; text-align: center; box-shadow: var(--shadow-elev-1); transition: box-shadow 0.12s ease, transform 0.08s ease, opacity 0.12s ease; }
    .modal-actions > *:hover { box-shadow: var(--shadow-elev-2); transform: translateY(-1px); }
    .modal-actions > *:active { transform: translateY(0); box-shadow: var(--shadow-elev-1); }
    .cancel-btn { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
    .submit-btn { background: var(--color-accent); color: var(--color-on-accent); }
    .btn-open { background: var(--color-purple); color: var(--color-on-purple); text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }
    .btn-add { background: var(--color-success); color: var(--color-on-success); }
  `]
})
export class MagnetDialogComponent {
  visible = signal(false);
  magnet = signal('');
  addToQbit?: () => void;

  open(magnet: string, addToQbit?: () => void): void {
    this.magnet.set(magnet);
    this.addToQbit = addToQbit;
    this.visible.set(true);
  }

  close(): void {
    this.visible.set(false);
  }

  copy(): void {
    navigator.clipboard.writeText(this.magnet()).then(() => {
      this.close();
    }).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = this.magnet();
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      this.close();
    });
  }

  onAdd(): void {
    if (this.addToQbit) {
      this.addToQbit();
    }
  }

  closeAfterOpen(): void {
    setTimeout(() => this.close(), 500);
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.close();
  }
}
