// IndexersComponent spec.
//
// CONST-XII anti-bluff narrative
// ------------------------------
// `TestDefaultTabIsConfigured` asserts the initial activeTab signal
//   value. A stub with wrong initial state would FAIL.
// `TestSetTabChangesActiveTab` calls setTab and asserts the signal
//   updates. A stub that ignored the parameter would FAIL.
// `TestOnIndexerAddedSwitchesToConfigured` calls onIndexerAdded and
//   asserts activeTab flips to 'configured' AND the refresh signal
//   increments. A stub that omitted the refresh bump would FAIL.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { IndexersComponent } from './indexers.component';
import { ConfiguredTabComponent } from './configured-tab.component';
import { CatalogTabComponent } from './catalog-tab.component';
import { HistoryTabComponent } from './history-tab.component';
import { IndexersService } from './indexers.service';
import { CredentialsService } from '../credentials/credentials.service';
import { of } from 'rxjs';

function setup() {
  TestBed.configureTestingModule({
    imports: [IndexersComponent, ConfiguredTabComponent, CatalogTabComponent, HistoryTabComponent],
    providers: [
      { provide: IndexersService, useValue: { list: vi.fn(() => of([])) } },
      { provide: CredentialsService, useValue: { list: vi.fn(() => of([])) } },
    ],
  });
  return TestBed.createComponent(IndexersComponent);
}

describe('IndexersComponent', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('TestDefaultTabIsConfigured', () => {
    const fixture = setup();
    expect(fixture.componentInstance.activeTab()).toBe('configured');
  });

  it('TestSetTabChangesActiveTab', () => {
    const fixture = setup();
    fixture.componentInstance.setTab('catalog');
    expect(fixture.componentInstance.activeTab()).toBe('catalog');
    fixture.componentInstance.setTab('history');
    expect(fixture.componentInstance.activeTab()).toBe('history');
  });

  it('TestOnIndexerAddedSwitchesToConfigured', () => {
    const fixture = setup();
    fixture.componentInstance.setTab('catalog');
    expect(fixture.componentInstance.activeTab()).toBe('catalog');
    const before = fixture.componentInstance.configuredRefresh();
    fixture.componentInstance.onIndexerAdded();
    expect(fixture.componentInstance.activeTab()).toBe('configured');
    expect(fixture.componentInstance.configuredRefresh()).toBe(before + 1);
  });
});
