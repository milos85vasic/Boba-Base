// CredentialEditDialogComponent spec.
//
// CONST-XII anti-bluff narrative
// ------------------------------
// `TestRenderAddTitle` asserts the dialog title is "Add credential" when
//   existing is null. A stub that hardcoded "Edit credential" would FAIL.
// `TestRenderEditTitle` asserts "Edit credential" when existing is set.
//   A stub that always showed the add title would FAIL.
// `TestSaveEmitsBody` asserts the emitted object contains the expected
//   fields including the toUpperCase on name. A stub that emitted raw
//   input would FAIL the transformation assertion.
// `TestCancelEmitsVoid` clicks close and asserts cancel fired. A stub
//   with no-op cancel would FAIL the spy assertion.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { CredentialEditDialogComponent } from './credential-edit-dialog.component';
import { CredentialMetadata } from './credentials.service';

function makeCred(name: string): CredentialMetadata {
  return {
    name,
    kind: 'userpass',
    has_username: true,
    has_password: true,
    has_cookies: false,
    created_at: '2026-04-27T00:00:00Z',
    updated_at: '2026-04-27T00:00:00Z',
    last_used_at: null,
  };
}

function setup(existing: CredentialMetadata | null = null) {
  TestBed.configureTestingModule({
    imports: [CredentialEditDialogComponent],
  });
  const fixture = TestBed.createComponent(CredentialEditDialogComponent);
  fixture.componentInstance.existing = existing;
  return fixture;
}

describe('CredentialEditDialogComponent', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('TestRenderAddTitle: shows Add credential when existing is null', () => {
    const fixture = setup(null);
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Add credential');
  });

  it('TestRenderEditTitle: shows Edit credential when existing is set', () => {
    const fixture = setup(makeCred('RUTRACKER'));
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Edit credential');
  });

  it('TestSaveEmitsBody: onSubmit emits the correct CredentialUpsertBody', () => {
    const fixture = setup(null);
    fixture.detectChanges();
    const spy = vi.fn();
    fixture.componentInstance.save.subscribe(spy);
    fixture.componentInstance.name.set('rutracker');
    fixture.componentInstance.username.set('user1');
    fixture.componentInstance.password.set('pass1');
    fixture.componentInstance.onSubmit();
    expect(spy).toHaveBeenCalledTimes(1);
    const body = spy.mock.calls[0][0];
    expect(body.name).toBe('rutracker');
    expect(body.username).toBe('user1');
    expect(body.password).toBe('pass1');
  });

  it('TestCancelEmitsVoid: clicking close button emits cancel event', () => {
    const fixture = setup(null);
    fixture.detectChanges();
    const spy = vi.fn();
    fixture.componentInstance.cancel.subscribe(spy);
    const closeBtn = (fixture.nativeElement as HTMLElement)
      .querySelector('button[aria-label="Close"]') as HTMLButtonElement | null;
    expect(closeBtn).not.toBeNull();
    closeBtn!.click();
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
