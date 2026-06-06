// IndexerAddDialogComponent spec.
//
// CONST-XII anti-bluff narrative
// ------------------------------
// `TestRendersRequiredFields` asserts each required_fields entry is in
//   the DOM. A stub that didn't iterate the array would FAIL.
// `TestCredentialDropdown` reads <option>.length and value. A stub
//   that ignored the credentials list would FAIL because the dropdown
//   would only contain the disabled placeholder.
// `TestSaveCallsConfigure` asserts service.configure was called with
//   the row id + the dropdown's value. A stub onSubmit that emitted
//   without calling configure would FAIL.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { IndexerAddDialogComponent } from './indexer-add-dialog.component';
import {
  IndexersService,
  CatalogItem,
} from './indexers.service';
import {
  CredentialsService,
  CredentialMetadata,
} from '../credentials/credentials.service';

function makeCred(name: string, kind: 'userpass' | 'cookie' = 'userpass'): CredentialMetadata {
  return {
    name,
    kind,
    has_username: kind === 'userpass',
    has_password: kind === 'userpass',
    has_cookies: kind === 'cookie',
    created_at: '2026-04-27T00:00:00Z',
    updated_at: '2026-04-27T00:00:00Z',
    last_used_at: null,
  };
}

function makeItem(id: string, required_fields: string[] = ['username', 'password']): CatalogItem {
  return {
    id,
    display_name: id.toUpperCase(),
    type: 'public',
    required_fields,
  };
}

function setup(opts: {
  item: CatalogItem | null;
  creds?: CredentialMetadata[];
  configure?: ReturnType<typeof vi.fn>;
  listFn?: ReturnType<typeof vi.fn>;
}) {
  const credService = {
    list: opts.listFn ?? vi.fn(() => of(opts.creds ?? [])),
    upsert: vi.fn(() => of({})),
    delete: vi.fn(() => of(undefined)),
  };
  const idxService = {
    configure: opts.configure ?? vi.fn(() => of({})),
    list: vi.fn(() => of([])),
    delete: vi.fn(() => of(undefined)),
    test: vi.fn(() => of({ status: 'ok' })),
    setEnabled: vi.fn(() => of({})),
    listCatalog: vi.fn(() => of({ total: 0, page: 1, page_size: 20, items: [] })),
    refreshCatalog: vi.fn(() => of({ refreshed_count: 0, errors: [] })),
    listRuns: vi.fn(() => of([])),
    getRun: vi.fn(() => of({})),
    triggerRun: vi.fn(() => of({})),
  };
  TestBed.configureTestingModule({
    imports: [IndexerAddDialogComponent],
    providers: [
      { provide: CredentialsService, useValue: credService },
      { provide: IndexersService, useValue: idxService },
    ],
  });
  const fixture = TestBed.createComponent(IndexerAddDialogComponent);
  fixture.componentInstance.item = opts.item;
  return { fixture, credService, idxService };
}

describe('IndexerAddDialogComponent', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('TestRendersRequiredFields: pre-populates the panel with required_fields', async () => {
    const { fixture } = setup({
      item: makeItem('rutracker', ['username', 'password']),
      creds: [makeCred('RUTRACKER')],
    });
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('username');
    expect(text).toContain('password');
    expect(text.toLowerCase()).toContain('rutracker');
  });

  it('TestCredentialDropdown: dropdown is populated from CredentialsService.list', async () => {
    const { fixture, credService } = setup({
      item: makeItem('rutracker'),
      creds: [makeCred('RUTRACKER'), makeCred('NNMCLUB', 'cookie')],
    });
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(credService.list).toHaveBeenCalledTimes(1);
    const select = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="credential-select"]') as HTMLSelectElement | null;
    expect(select).not.toBeNull();
    const options = Array.from(select!.querySelectorAll('option')) as HTMLOptionElement[];
    // First option is the disabled placeholder, then 2 real creds:
    expect(options.length).toBe(3);
    const values = options.map((o) => o.value);
    expect(values).toContain('RUTRACKER');
    expect(values).toContain('NNMCLUB');
  });

  it('TestSaveCallsConfigure: picking a credential and clicking Save fires service.configure', async () => {
    const configureSpy = vi.fn(() => of({}));
    const { fixture, idxService } = setup({
      item: makeItem('rutracker'),
      creds: [makeCred('RUTRACKER')],
      configure: configureSpy,
    });
    let savedFired = false;
    fixture.componentInstance.saved.subscribe(() => (savedFired = true));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="credential-select"]') as HTMLSelectElement;
    select.value = 'RUTRACKER';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const saveBtn = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="save-indexer"]') as HTMLButtonElement | null;
    expect(saveBtn).not.toBeNull();
    expect(saveBtn!.disabled).toBe(false);
    saveBtn!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(idxService.configure).toHaveBeenCalledTimes(1);
    expect(idxService.configure).toHaveBeenCalledWith('rutracker', { credential_name: 'RUTRACKER' });
    expect(savedFired).toBe(true);
  });

  it('TestCancelDoesNotConfigure: clicking the close button emits cancel without calling configure', async () => {
    const configureSpy = vi.fn(() => of({}));
    const { fixture, idxService } = setup({
      item: makeItem('rutracker'),
      creds: [makeCred('RUTRACKER')],
      configure: configureSpy,
    });
    let cancelFired = false;
    fixture.componentInstance.cancel.subscribe(() => (cancelFired = true));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const closeBtn = (fixture.nativeElement as HTMLElement)
      .querySelector('button[aria-label="Close"]') as HTMLButtonElement | null;
    expect(closeBtn).not.toBeNull();
    closeBtn!.click();

    expect(cancelFired).toBe(true);
    expect(idxService.configure).not.toHaveBeenCalled();
  });

  // --- Error + cookie-flow coverage (lines 181, 197, 206-222). ---

  it('TestListErrorRendersAlert: a failing CredentialsService.list surfaces the unwrapped error in the dialog', async () => {
    const { fixture } = setup({
      item: makeItem('rutracker'),
      listFn: vi.fn(() => throwError(() => ({ error: { error: 'creds endpoint 500' } }))),
    });
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const alert = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="dialog-error"]');
    expect(alert?.textContent?.trim()).toBe('creds endpoint 500');
  });

  it('TestConfigureErrorRendersAlert: a failing configure renders the error and does NOT emit (saved)', async () => {
    const { fixture, idxService } = setup({
      item: makeItem('rutracker'),
      creds: [makeCred('RUTRACKER')],
      configure: vi.fn(() => throwError(() => 'configure exploded')),
    });
    let savedFired = false;
    fixture.componentInstance.saved.subscribe(() => (savedFired = true));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="credential-select"]') as HTMLSelectElement;
    select.value = 'RUTRACKER';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[data-testid="save-indexer"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(idxService.configure).toHaveBeenCalledTimes(1);
    expect(savedFired).toBe(false);
    const alert = (fixture.nativeElement as HTMLElement)
      .querySelector('[data-testid="dialog-error"]');
    // errorMessage() stringified the primitive thrown value.
    expect(alert?.textContent?.trim()).toBe('configure exploded');
  });

  it('TestCookieOnlyFlowRenders: a cookie-only indexer renders the IPTorrents flow instead of the credential form', async () => {
    const { fixture } = setup({
      // cookie field present, no username/password → isCookieOnly() true.
      item: makeItem('iptorrents', ['cookieheader']),
    });
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(fixture.componentInstance.isCookieOnly()).toBe(true);
    expect(el.querySelector('app-iptorrents-cookie-flow')).not.toBeNull();
    // The plain credential form must NOT be present in cookie-only mode.
    expect(el.querySelector('[data-testid="credential-select"]')).toBeNull();
  });

  it('TestCookieFlowSavedEmits: onCookieFlowSaved bubbles up as (saved)', async () => {
    const { fixture } = setup({ item: makeItem('iptorrents', ['cookieheader']) });
    let savedCount = 0;
    fixture.componentInstance.saved.subscribe(() => savedCount++);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    fixture.componentInstance.onCookieFlowSaved();
    expect(savedCount).toBe(1);
  });
});
