import { Component, ChangeDetectionStrategy } from '@angular/core';

/**
 * Site footer — "Made with ❤ by Vasic Digital".
 *
 * Originally added in commit 368d7fe to the legacy server-rendered
 * dashboard.html. Lost during the Angular 19 port (bb2aec4) and
 * restored here as a first-class standalone component that lives on
 * every page by virtue of being mounted in AppComponent.
 *
 * All colours are sourced from the design-system CSS variables so
 * the footer follows whatever palette is active.
 */
@Component({
  selector: 'app-site-footer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <footer class="site-footer" role="contentinfo">
      Made with
      <span class="heart" aria-label="love">&#10084;</span>
      by
      <a
        href="https://www.vasic.digital"
        target="_blank"
        rel="noopener noreferrer"
        class="vd-link"
      >Vasic Digital</a>
    </footer>
  `,
  styles: [`
    .site-footer {
      text-align: center;
      padding: 22px 16px;
      margin-top: 28px;
      border-top: 1px solid var(--color-border);
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .site-footer .heart {
      color: var(--color-accent-text);
      margin: 0 2px;
      display: inline-block;
      animation: footer-heart-pulse 1.6s ease-in-out infinite;
      /* Blood-red heart on any palette — small shadow so it keeps
       * contrast against the muted footer text. */
      text-shadow: var(--shadow-text-sm);
    }
    .site-footer .vd-link {
      color: var(--color-accent-text);
      text-decoration: none;
      font-weight: 600;
      margin-left: 4px;
      text-shadow: var(--shadow-text-sm);
    }
    .site-footer .vd-link:hover,
    .site-footer .vd-link:focus-visible {
      text-decoration: underline;
      color: var(--color-accent-hover);
    }
    @keyframes footer-heart-pulse {
      0%, 100% { transform: scale(1); }
      50%      { transform: scale(1.15); }
    }
    @media (prefers-reduced-motion: reduce) {
      .site-footer .heart { animation: none; }
    }
  `]
})
export class SiteFooterComponent {}
